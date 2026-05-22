// YAML compiler/decompiler. Uses ONLY the parser the backend already accepts.
// We do NOT import a yaml library; we emit a deterministic, parser-friendly
// shape by hand. This is safe because the SkillFile schema is small + closed.

import type {
  AnyStepBlock,
  SkillFileDoc,
  TriggerMatcher,
} from "./types";

let _localIdCounter = 0;
export function newLocalId(): string {
  _localIdCounter += 1;
  return `loc_${_localIdCounter}_${Math.random().toString(36).slice(2, 8)}`;
}

// ── DECOMPILE: parse YAML text into the block IR (best-effort, server is
//    authoritative). We rely on a minimal hand-written YAML reader because the
//    schema is closed and we don't want a new dep. If parsing fails, throw —
//    the caller falls back to YAML-only mode.

export class DecompileError extends Error {}

// Minimal YAML reader for our subset. Handles:
//   - mappings (key: value)
//   - sequences (- item)
//   - scalar strings, ints, bools, nulls
//   - flow lists ([a, b, c])
//   - block strings (no folding/indent quirks)
// Does NOT handle anchors, multi-doc, or tags.
//
// IMPORTANT: We do NOT bypass the backend's safe_load. This is only for the
// EDIT path on already-validated YAML. On Save, the backend re-parses with
// PyYAML — that is the source of truth.

type YamlValue =
  | string
  | number
  | boolean
  | null
  | YamlValue[]
  | { [k: string]: YamlValue };

function parseYaml(text: string): YamlValue {
  // Strategy: split into lines, track indent, recursively assemble. For the
  // SkillFile schema this is enough. If parsing throws, caller handles it.
  const lines = text.split(/\r?\n/).map((line) => line.replace(/\s+$/, ""));
  // Skip leading blanks + comments
  let i = 0;
  while (
    i < lines.length &&
    (lines[i].trim() === "" || lines[i].trim().startsWith("#"))
  )
    i += 1;

  const parseValue = (raw: string): YamlValue => {
    const trimmed = raw.trim();
    if (trimmed === "" || trimmed === "~" || trimmed === "null") return null;
    if (trimmed === "true") return true;
    if (trimmed === "false") return false;
    if (/^-?\d+$/.test(trimmed)) return Number.parseInt(trimmed, 10);
    if (/^-?\d+\.\d+$/.test(trimmed)) return Number.parseFloat(trimmed);
    // Flow list: [a, b, c]
    if (trimmed.startsWith("[") && trimmed.endsWith("]")) {
      const inner = trimmed.slice(1, -1).trim();
      if (inner === "") return [];
      return inner.split(",").map((part) => parseValue(part));
    }
    // Quoted string
    if (
      (trimmed.startsWith('"') && trimmed.endsWith('"')) ||
      (trimmed.startsWith("'") && trimmed.endsWith("'"))
    ) {
      return trimmed.slice(1, -1);
    }
    return trimmed;
  };

  // Recursive descent on indent
  const indentOf = (line: string): number => {
    let n = 0;
    while (n < line.length && line[n] === " ") n += 1;
    return n;
  };

  const parseBlock = (
    baseIndent: number,
    startIdx: number,
  ): [YamlValue, number] => {
    if (startIdx >= lines.length) return [null, startIdx];
    const firstLine = lines[startIdx];
    if (firstLine.trim() === "") return parseBlock(baseIndent, startIdx + 1);
    const ind = indentOf(firstLine);
    if (ind < baseIndent) return [null, startIdx];

    // Sequence
    if (firstLine.trim().startsWith("- ")) {
      const items: YamlValue[] = [];
      let idx = startIdx;
      while (idx < lines.length) {
        const line = lines[idx];
        if (line.trim() === "" || line.trim().startsWith("#")) {
          idx += 1;
          continue;
        }
        if (indentOf(line) < ind) break;
        if (indentOf(line) === ind && line.trim().startsWith("- ")) {
          // Read the item; first content is what follows "- "
          const headIndent = ind;
          const headRest = line.slice(headIndent + 2);
          // If headRest is "key: value", treat as start of a mapping
          if (/^[\w-]+\s*:/.test(headRest)) {
            // Reconstruct the mapping with the proper indent. Build a virtual
            // block: replace this line's leading "- " with two spaces, then
            // parse the following lines that belong to this item.
            const itemLines: string[] = [
              " ".repeat(headIndent + 2) + headRest,
            ];
            idx += 1;
            while (idx < lines.length) {
              const next = lines[idx];
              if (next.trim() === "" || next.trim().startsWith("#")) {
                idx += 1;
                continue;
              }
              if (indentOf(next) > headIndent) {
                itemLines.push(next);
                idx += 1;
              } else {
                break;
              }
            }
            const sub = parseYamlSlice(itemLines, headIndent + 2);
            items.push(sub);
          } else if (headRest === "") {
            // Multi-line item starting with "-" alone
            idx += 1;
            const itemLines: string[] = [];
            while (idx < lines.length) {
              const next = lines[idx];
              if (next.trim() === "" || next.trim().startsWith("#")) {
                idx += 1;
                continue;
              }
              if (indentOf(next) > headIndent) {
                itemLines.push(next);
                idx += 1;
              } else break;
            }
            const sub = parseYamlSlice(itemLines, headIndent + 2);
            items.push(sub);
          } else {
            items.push(parseValue(headRest));
            idx += 1;
          }
        } else if (indentOf(line) === ind) {
          break;
        } else {
          idx += 1;
        }
      }
      return [items, idx];
    }

    // Mapping
    const map: { [k: string]: YamlValue } = {};
    let idx = startIdx;
    while (idx < lines.length) {
      const line = lines[idx];
      if (line.trim() === "" || line.trim().startsWith("#")) {
        idx += 1;
        continue;
      }
      if (indentOf(line) < ind) break;
      if (indentOf(line) > ind) {
        idx += 1;
        continue;
      }
      const m = line.match(/^(\s*)([^:]+):\s*(.*)$/);
      if (!m) {
        idx += 1;
        continue;
      }
      const key = m[2].trim();
      const rest = m[3];
      if (rest.trim() === "") {
        // Nested block
        const [nested, nextIdx] = parseBlock(ind + 2, idx + 1);
        map[key] = nested;
        idx = nextIdx;
      } else {
        map[key] = parseValue(rest);
        idx += 1;
      }
    }
    return [map, idx];
  };

  const parseYamlSlice = (
    sliceLines: string[],
    baseIndent: number,
  ): YamlValue => {
    // Re-enter parseBlock against a sliced array
    const saved = lines.slice();
    lines.length = 0;
    lines.push(...sliceLines);
    const [val] = parseBlock(baseIndent, 0);
    lines.length = 0;
    lines.push(...saved);
    return val;
  };

  const [doc] = parseBlock(0, i);
  return doc;
}

export function decompile(yamlText: string): SkillFileDoc {
  let raw: YamlValue;
  try {
    raw = parseYaml(yamlText);
  } catch (err) {
    throw new DecompileError(
      `unable to parse YAML: ${err instanceof Error ? err.message : String(err)}`,
    );
  }
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    throw new DecompileError("YAML root must be a mapping");
  }
  const obj = raw as Record<string, YamlValue>;
  const triggers = Array.isArray(obj.when_triggered_by)
    ? obj.when_triggered_by
    : [];
  const steps = Array.isArray(obj.steps) ? obj.steps : [];

  const toTrigger = (t: YamlValue): TriggerMatcher => {
    const tm = (t ?? {}) as Record<string, YamlValue>;
    const src = tm.source;
    return {
      intent: typeof tm.intent === "string" ? tm.intent : "",
      source: Array.isArray(src) ? src.map((s) => String(s)) : [],
    };
  };

  const toStep = (s: YamlValue): AnyStepBlock => {
    const sm = (s ?? {}) as Record<string, YamlValue>;
    const type = String(sm.type);
    const id = String(sm.id ?? "");
    const lid = newLocalId();
    if (type === "if_then") {
      const nested = Array.isArray(sm.then) ? sm.then : [];
      return {
        _localId: lid,
        type: "if_then",
        id,
        condition: typeof sm.condition === "string" ? sm.condition : "",
        then: nested.map(toStep),
      };
    }
    if (type === "fetch_entity") {
      return {
        _localId: lid,
        type: "fetch_entity",
        id,
        query: typeof sm.query === "string" ? sm.query : "",
        bind_to: typeof sm.bind_to === "string" ? sm.bind_to : "",
      };
    }
    if (type === "write_entity") {
      const data =
        sm.data && typeof sm.data === "object" && !Array.isArray(sm.data)
          ? (sm.data as Record<string, unknown>)
          : {};
      return {
        _localId: lid,
        type: "write_entity",
        id,
        cluster: typeof sm.cluster === "string" ? sm.cluster : "",
        entity_type: typeof sm.entity_type === "string" ? sm.entity_type : "",
        data,
      };
    }
    if (type === "require_approval") {
      return {
        _localId: lid,
        type: "require_approval",
        id,
        role: typeof sm.role === "string" ? sm.role : "",
        timeout_seconds:
          typeof sm.timeout_seconds === "number" ? sm.timeout_seconds : 3600,
      };
    }
    if (type === "log_decision") {
      return {
        _localId: lid,
        type: "log_decision",
        id,
        cluster: typeof sm.cluster === "string" ? sm.cluster : "",
        note: typeof sm.note === "string" ? sm.note : "",
      };
    }
    throw new DecompileError(`unknown step type: ${type}`);
  };

  return {
    name: typeof obj.name === "string" ? obj.name : "",
    description: typeof obj.description === "string" ? obj.description : "",
    version: typeof obj.version === "number" ? obj.version : 1,
    when_triggered_by: triggers.map(toTrigger),
    steps: steps.map(toStep),
  };
}

// ── COMPILE: emit YAML the backend parser accepts. Deterministic indent + key
//    order. No fancy formatting; readable enough.

function indentStr(n: number): string {
  return " ".repeat(n);
}

function emitString(s: string): string {
  // Quote if contains : { } [ ] # & * ! | > ' " % @ ` , or starts with -
  if (s === "") return '""';
  if (/[:{}[\]#&*!|>'"%@`,]|^-/.test(s)) {
    return JSON.stringify(s);
  }
  return s;
}

function emitTrigger(t: TriggerMatcher, ind: number): string {
  const lines: string[] = [];
  lines.push(`${indentStr(ind)}- intent: ${emitString(t.intent)}`);
  if (t.source && t.source.length > 0) {
    lines.push(
      `${indentStr(ind + 2)}source: [${t.source
        .map((s) => emitString(s))
        .join(", ")}]`,
    );
  }
  return lines.join("\n");
}

function emitData(data: Record<string, unknown>, ind: number): string {
  const lines: string[] = [];
  for (const [k, v] of Object.entries(data)) {
    if (typeof v === "string") {
      lines.push(`${indentStr(ind)}${k}: ${emitString(v)}`);
    } else if (typeof v === "number" || typeof v === "boolean") {
      lines.push(`${indentStr(ind)}${k}: ${v}`);
    } else if (v === null || v === undefined) {
      lines.push(`${indentStr(ind)}${k}: null`);
    } else if (Array.isArray(v)) {
      lines.push(
        `${indentStr(ind)}${k}: [${v
          .map((x) => (typeof x === "string" ? emitString(x) : JSON.stringify(x)))
          .join(", ")}]`,
      );
    } else if (typeof v === "object") {
      lines.push(`${indentStr(ind)}${k}:`);
      lines.push(emitData(v as Record<string, unknown>, ind + 2));
    }
  }
  return lines.join("\n");
}

function emitStep(s: AnyStepBlock, ind: number): string {
  const lines: string[] = [];
  lines.push(`${indentStr(ind)}- id: ${emitString(s.id)}`);
  lines.push(`${indentStr(ind + 2)}type: ${s.type}`);
  if (s.type === "if_then") {
    lines.push(`${indentStr(ind + 2)}condition: ${emitString(s.condition)}`);
    if (s.then.length > 0) {
      lines.push(`${indentStr(ind + 2)}then:`);
      for (const nested of s.then) {
        lines.push(emitStep(nested, ind + 4));
      }
    } else {
      lines.push(`${indentStr(ind + 2)}then: []`);
    }
  } else if (s.type === "fetch_entity") {
    lines.push(`${indentStr(ind + 2)}query: ${emitString(s.query)}`);
    lines.push(`${indentStr(ind + 2)}bind_to: ${emitString(s.bind_to)}`);
  } else if (s.type === "write_entity") {
    lines.push(`${indentStr(ind + 2)}cluster: ${emitString(s.cluster)}`);
    lines.push(`${indentStr(ind + 2)}entity_type: ${emitString(s.entity_type)}`);
    if (Object.keys(s.data).length > 0) {
      lines.push(`${indentStr(ind + 2)}data:`);
      lines.push(emitData(s.data, ind + 4));
    } else {
      lines.push(`${indentStr(ind + 2)}data: {}`);
    }
  } else if (s.type === "require_approval") {
    lines.push(`${indentStr(ind + 2)}role: ${emitString(s.role)}`);
    if (s.timeout_seconds !== 3600) {
      lines.push(`${indentStr(ind + 2)}timeout_seconds: ${s.timeout_seconds}`);
    }
  } else if (s.type === "log_decision") {
    lines.push(`${indentStr(ind + 2)}cluster: ${emitString(s.cluster)}`);
    lines.push(`${indentStr(ind + 2)}note: ${emitString(s.note)}`);
  }
  return lines.join("\n");
}

export function compile(doc: SkillFileDoc): string {
  const lines: string[] = [];
  lines.push(`name: ${emitString(doc.name)}`);
  lines.push(`description: ${emitString(doc.description)}`);
  lines.push(`version: ${doc.version}`);
  lines.push(`when_triggered_by:`);
  for (const t of doc.when_triggered_by) {
    lines.push(emitTrigger(t, 2));
  }
  lines.push(`steps:`);
  for (const s of doc.steps) {
    lines.push(emitStep(s, 2));
  }
  return lines.join("\n") + "\n";
}
