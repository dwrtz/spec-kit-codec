---
description: "Turn a Spec Kit feature folder into a Spekkr spec folder"
---

# Export to a Spekkr spec

Turn a Spec Kit feature folder into a [Spekkr](https://spekkr.com) spec
folder that Spekkr's `check_spec` and `publish_spec` accept. If the feature
came from Spekkr in the first place, the result is the original spec, byte for
byte.

## User Input

```text
$ARGUMENTS
```

The input is the feature folder, such as `specs/003-pebble-jar`. After it
come the options `--dir <spekkr-folder>`, `--author <username>`,
`--date YYYY-MM-DD` and `--platforms web,cli`. If no feature folder was given,
use the active one from `.specify/feature.json`. If there is none, ask.

## Steps

1. Find out whether the feature folder has a `spekkr.json`.
   - If it does, the script copies it unchanged. The `--author`, `--date`
     and `--platforms` options are not used.
   - If it does not, the script fills one in and `--author` is required. It
     is the person's Spekkr username. Ask for it if it was not given. Do not
     invent one.

2. Run from the project root:

   ```bash
   python3 .specify/extensions/spekkr/spec_kit_codec.py to-spekkr <FEATURE_FOLDER> [--dir <SPEKKR_FOLDER>] [--author <USERNAME>] [--date <YYYY-MM-DD>] [--platforms <LIST>]
   ```

3. The script prints the Spekkr folder it wrote on stdout. If it prints a line
   that starts with `error:` and exits with a non-zero status, nothing was
   written. Show the error and stop. A `design.md` that is not the codec's
   own stub is one cause. A target folder that already has files is another.

4. When the script filled in a manifest, it prints notes on stderr, including
   the summary it chose. Show those notes to the person. Ask them to edit the
   summary and the display name in `spekkr.json` before publishing.

5. Tell the person the folder is ready to check and publish with Spekkr's
   `check_spec` and `publish_spec`. Do not publish for them.

## Rules

- Do not edit the feature folder. The script only reads it.
- Do not change the generated `spekkr.json` beyond what the person asks for.
- Do not publish anything. Publishing is the person's decision.
