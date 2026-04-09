---
name: wedge100s-doc-check
description: Use when committing code changes to any wedge100s topic branch — verifies Python docstrings and C Doxygen headers are present on all modified functions before allowing the commit
---

# Wedge 100S Documentation Check

## Overview

Every code change on a wedge100s topic branch must include documentation for modified functions. This skill verifies coverage before commit.

## When to Use

- Before any `git commit` that includes `.py` or `.c` files under `wedge100s-32x/`
- After adding a new function or method
- After changing a function signature or return value

## Verification Procedure

### Step 1: Identify Modified Files

```bash
cd /export/sonic/sonic-buildimage
W=platform/broadcom/sonic-platform-modules-accton/wedge100s-32x

# Staged files only
git diff --cached --name-only -- "$W/**/*.py" "$W/**/*.c"
```

If no `.py` or `.c` files are staged, skip — no doc check needed.

### Step 2: Check Python Files

For each staged `.py` file, verify every public method has a docstring:

```bash
python3 -c "
import ast, sys
for fpath in sys.argv[1:]:
    with open(fpath) as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith('_') and node.name != '__init__':
                continue
            if not (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, (ast.Constant, ast.Str))):
                print(f'  MISSING: {fpath}:{node.lineno} {node.name}()')
" <files>
```

**Required docstring format** (Google-style):
- One-line summary (always)
- `Args:` section (when method takes parameters beyond `self`)
- `Returns:` section (when method returns a value)

### Step 3: Check C Files

For each staged `.c` file, verify every function has a Doxygen header:

```bash
for f in <files>; do
  # Count functions (non-static + static)
  funcs=$(grep -cE '^(static )?(int|void|ssize_t|struct|const|unsigned) ' "$f")
  # Count @brief markers
  briefs=$(grep -c '@brief' "$f")
  echo "  $f: $funcs functions, $briefs @brief markers"
  if [ "$briefs" -lt "$funcs" ]; then
    echo "  MISSING: $((funcs - briefs)) functions without @brief"
  fi
done
```

**Required Doxygen format:**
- `@brief` description (always)
- `@param` for each parameter
- `@return` for non-void functions

### Step 4: Report and Block

If any gaps found:
1. Print the list of undocumented functions
2. **Do not proceed with the commit**
3. Add the missing docstrings/Doxygen on the same branch, in the same commit

## What Requires Documentation

| Change | Required |
|--------|----------|
| New function/method | Full docstring + Args/Returns |
| Changed signature | Update Args/params |
| Changed return value | Update Returns/@return |
| Changed behavior | Update description |
| New file | Module-level docstring + all functions |
| Private method (`_name`) | Not required (but encouraged) |
| `__init__` | Required (Args section) |

## Common Mistakes

- Adding docstrings on `wedge100s/docs` instead of the source branch — **wrong**. Docs go with the code.
- Writing "see parent class" instead of a real docstring — **wrong**. Each method documents its platform-specific behavior.
- Committing code "to fix later" — **wrong**. Documentation is part of the commit, not a follow-up.
