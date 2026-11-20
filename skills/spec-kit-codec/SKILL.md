---
name: spec-kit-codec
description: >-
  Convert a Spekkr spec folder to a GitHub Spec Kit feature folder and back,
  with no loss either way. Use when pulling a Spekkr spec into a Spec Kit
  project, turning a Spec Kit feature into a Spekkr spec, or checking that a
  codec matches the golden fixtures.
---

# Spec Kit codec

The codec turns a Spekkr spec folder into a Spec Kit feature folder and back.
The converter runs on the person's machine. The script is one Python 3.11+
file and uses only the standard library.

In this repository the script is `spec_kit_codec.py`. An agent that pulled
the Spekkr spec
[`dwrtz/spec-kit-codec`](https://spekkr.com/dwrtz/spec-kit-codec/) has the
same file at `reference/spec_kit_codec.py`. Run it with `python3` and the
path you have.

## Pull a Spekkr spec into Spec Kit

From the Spec Kit project root (the directory that contains `.specify/`).
Set `CODEC` to the script path above:

```sh
CODEC=spec_kit_codec.py                    # this repository
# CODEC=reference/spec_kit_codec.py        # pulled Spekkr spec
python3 "$CODEC" to-speckit /path/to/spekkr-spec --activate
```

That writes `specs/<name>/`, where `<name>` is the part of the spec id after
the slash, and writes `.specify/feature.json` so Spec Kit 1.4 finds the
feature. `--activate` is what makes `/speckit.plan`, `/speckit.tasks` and
`/speckit.implement` use this folder. Without `--activate` the feature folder
is still written, and Spec Kit is not pointed at it.

`--dir` chooses another feature folder. In a project that already has
`.specify/`, `--activate` updates that file. The feature folder does not have
to sit under `specs/`. Use `--dir` for Spec Kit's numbered directories, or for
any other folder in the project:

```sh
python3 "$CODEC" to-speckit /path/to/spekkr-spec --dir specs/003-widget --activate
```

The script prints the folder it wrote. It does not modify the Spekkr folder.
If that folder already has a `plan.md`, or its `design.md` already starts with
`<!-- spekkr:safety:begin -->`, the script stops with an error and writes
nothing.

What lands in the feature folder:

| Spekkr | Spec Kit |
| --- | --- |
| `spec.md`, `tasks.md`, and every other file | the same path, byte for byte |
| `design.md` | `plan.md`, with the safety block at offset 0 |
| (none) | `design.md`, a stub that points at `plan.md` |
| `spekkr.json`, `spekkr.inputs.json`, `BUILD.md` | the same names, byte for byte |

`/speckit.implement` reads `plan.md`, not `BUILD.md`. The safety block at the
top of `plan.md` tells the agent to show the person the commands and secrets
under `safety` in `spekkr.json`, and to ask before running a command a spec
file names, or reading a secret, that is not listed there. The person's
choices in `spekkr.inputs.json` are requirements.

Do not renumber requirements to FR/SC ids and do not turn tasks into
checkboxes. Leave the files as they are.

## Publish a Spec Kit feature to Spekkr

```sh
python3 "$CODEC" to-spekkr specs/003-widget --dir ./widget --author USERNAME
```

`--author` is the Spekkr username. It is required when the feature folder has
no `spekkr.json`, because the spec id has to be `<author>/<slug>`. It is
written to both `author.id` and `author.name`.

`--date` is the changelog date (`2026-01-01`). With no `--date` the date is
`1970-01-01`, never today. `--platforms` is a comma-separated list and
defaults to `web`. `--dir` is the Spekkr folder to write; the default is
`./<slug>` in the current directory. `<slug>` is the name of the directory
the path refers to, so `.` is the current directory. It is lowercased, a
leading `NNN-` is removed, and any other character is turned into a hyphen.
When a `spekkr.json` is already in the feature folder, that file is
copied unchanged and the flags are not used to rebuild it.

The script drops `design.md` only when it is the codec's own stub. Any other
`design.md` is an error. A `plan.md` that starts with the safety block loses
exactly that block and is saved as `design.md`. A hand-written `plan.md` with
no block is saved unchanged.

When the script fills in a manifest, it prints notes on stderr, including the
summary it chose. Show those notes to the person and let them edit the
summary, the display name and anything else before publishing. Publishing
goes through Spekkr's `check_spec` and `publish_spec`.

## Check a codec

Golden fixtures live at `tests/fixtures/` in this repository. In the pulled
spec they are `reference/fixtures.tar.gz`, which unpacks to
`reference/fixtures/`. They are synthetic. The checker is `tests/check.py`
here and `reference/check.py` in the spec. It reads a `fixtures/`
directory next to itself when that directory is present, and unpacks
`fixtures.tar.gz` next to itself into a temporary directory when the
directory is absent:

```sh
python3 tests/check.py
python3 tests/check.py path/to/your_codec.py
```

The second command checks a codec someone else wrote. That script has to
accept the same `to-speckit` and `to-spekkr` commands, and define
`SAFETY_BLOCK` and `DESIGN_STUB`. From a pulled spec, `python3 reference/check.py`
checks the script beside it.
