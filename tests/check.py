#!/usr/bin/env python3
"""Round-trip the Spec Kit codec and compare it with the golden fixtures.

From this repository:

    python3 tests/check.py
    python3 tests/check.py path/to/your_codec.py

The optional argument is a self-built codec. It has to accept the same
commands as spec_kit_codec.py, and the module has to define SAFETY_BLOCK
and DESIGN_STUB.

A copy that sits in a directory named reference, next to spec_kit_codec.py
and fixtures/, checks that copy. That is the layout of the Spekkr spec
dwrtz/spec-kit-codec.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    codec_path, fixtures, custom = locate()
    codec = load_codec(codec_path)
    failures: list[str] = []
    check_spekkr(codec_path, codec, fixtures / "spekkr", failures)
    check_handwritten(codec_path, codec, fixtures / "handwritten", failures)
    check_flags(codec_path, codec, fixtures, failures)
    if not custom and HERE.name != "reference":
        check_documented_bytes(codec, failures)
    if failures:
        print(f"{len(failures)} Spec Kit codec check(s) failed:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1
    where = "reference fixtures" if HERE.name == "reference" else "tests/fixtures"
    print(f"Spec Kit codec checks passed ({where}).")
    return 0


def locate() -> tuple[Path, Path, bool]:
    """The codec, the fixtures, and whether the caller named another codec."""
    if len(sys.argv) > 2:
        raise SystemExit("usage: python3 tests/check.py [CODEC.py]")
    override = Path(sys.argv[1]) if len(sys.argv) == 2 else None
    if HERE.name == "reference":
        codec = HERE / "spec_kit_codec.py"
        fixtures = HERE / "fixtures"
    else:
        codec = HERE.parent / "spec_kit_codec.py"
        fixtures = HERE / "fixtures"
    custom = override is not None
    if custom:
        codec = override
    # Flag checks run the script with a different cwd. A relative path would
    # then be looked up inside that temporary directory.
    codec = codec.resolve()
    if not codec.is_file():
        raise SystemExit(f"codec not found: {codec}")
    if not fixtures.is_dir():
        raise SystemExit(f"fixtures not found: {fixtures}")
    return codec, fixtures, custom


def load_codec(path: Path):
    spec = importlib.util.spec_from_file_location("spec_kit_codec", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_documented_bytes(codec, failures: list[str]) -> None:
    """The README quotes the block and the stub, so those bytes cannot drift."""
    readme = HERE.parent / "README.md"
    if not readme.is_file():
        failures.append("docs: README.md is missing")
        return
    text = readme.read_bytes()
    if codec.SAFETY_BLOCK not in text:
        failures.append("docs: README.md does not contain the safety block bytes")
    if codec.DESIGN_STUB not in text:
        failures.append("docs: README.md does not contain the design stub bytes")


def check_spekkr(codec_path: Path, codec, root: Path, failures: list[str]) -> None:
    for case in cases(root):
        label = f"spekkr/{case.name}"
        source = case / "source"
        if (case / "error.txt").is_file():
            expect_error(codec_path, ["to-speckit", str(source), "--dir", "out"], case, label, failures)
            continue
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            feature = tmp_path / "feature"
            back = tmp_path / "back"
            forward = run(codec_path, ["to-speckit", str(source), "--dir", str(feature)])
            if not ok(forward, label, "to-speckit", failures):
                continue
            if forward.stderr:
                failures.append(f"{label}: to-speckit wrote to stderr: {forward.stderr!r}")
            backward = run(codec_path, ["to-spekkr", str(feature), "--dir", str(back)])
            if not ok(backward, label, "to-spekkr", failures):
                continue
            if backward.stderr:
                failures.append(f"{label}: to-spekkr wrote to stderr: {backward.stderr!r}")
            differ(source, back, f"{label}: round trip", failures)
            differ(case / "expected", feature, f"{label}: golden feature folder", failures)
            assert_safety(codec, source, feature, label, failures)


def check_handwritten(codec_path: Path, codec, root: Path, failures: list[str]) -> None:
    flags = ["--author", "example-user", "--date", "2026-01-01"]
    for case in cases(root):
        label = f"handwritten/{case.name}"
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = place(case, tmp_path / "placed")
            if (case / "error.txt").is_file():
                expect_error(
                    codec_path,
                    ["to-spekkr", str(source), "--dir", str(tmp_path / "out"), *flags],
                    case,
                    label,
                    failures,
                )
                continue
            spekkr = tmp_path / "spekkr"
            fixed = tmp_path / "fixed"
            again_spekkr = tmp_path / "again-spekkr"
            again_fixed = tmp_path / "again-fixed"
            first = run(codec_path, ["to-spekkr", str(source), "--dir", str(spekkr), *flags])
            if not ok(first, label, "to-spekkr", failures):
                continue
            feature = run(codec_path, ["to-speckit", str(spekkr), "--dir", str(fixed)])
            if not ok(feature, label, "to-speckit", failures):
                continue
            second = run(codec_path, ["to-spekkr", str(fixed), "--dir", str(again_spekkr), *flags])
            if not ok(second, label, "to-spekkr again", failures):
                continue
            third = run(codec_path, ["to-speckit", str(again_spekkr), "--dir", str(again_fixed)])
            if not ok(third, label, "to-speckit again", failures):
                continue
            differ(fixed, again_fixed, f"{label}: fixed point", failures)
            differ(spekkr, again_spekkr, f"{label}: to-spekkr is stable", failures)
            differ(case / "expected-spekkr", spekkr, f"{label}: golden Spekkr folder", failures)
            differ(case / "expected-fixed", fixed, f"{label}: golden fixed point", failures)
            plan = (source / "plan.md").read_bytes()
            design = (spekkr / "design.md").read_bytes()
            if design != plan:
                failures.append(f"{label}: design.md is not the original plan.md")
            stub = (fixed / "design.md").read_bytes()
            if stub != codec.DESIGN_STUB:
                failures.append(f"{label}: fixed design.md is not the codec stub")
            fixed_plan = (fixed / "plan.md").read_bytes()
            if not fixed_plan.startswith(codec.SAFETY_BLOCK):
                failures.append(f"{label}: fixed plan.md does not start with the safety block")
            elif fixed_plan[len(codec.SAFETY_BLOCK) :] != plan:
                failures.append(f"{label}: stripping the safety block does not restore plan.md")
            if case.name == "long-summary":
                summary = json.loads((spekkr / "spekkr.json").read_text(encoding="utf-8"))["summary"]
                words = summary.split(" ")
                if len(summary) > 140 or not words or words[-1] != "pebble":
                    failures.append(
                        f"{label}: summary is {len(summary)} characters and ends {summary[-20:]!r}"
                    )


def check_flags(codec_path: Path, codec, fixtures: Path, failures: list[str]) -> None:
    basic = fixtures / "spekkr" / "basic" / "source"
    plain = fixtures / "handwritten" / "plain"
    numbered = fixtures / "handwritten" / "numbered"
    if not basic.is_dir() or not plain.is_dir() or not numbered.is_dir():
        failures.append("flags: basic, plain or numbered fixture is missing")
        return

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        default = run(codec_path, ["to-speckit", str(basic)], cwd=tmp_path)
        feature = tmp_path / "specs" / "basic"
        if default.returncode != 0 or not feature.is_dir():
            failures.append(
                f"flags: default feature folder specs/basic was not written ({default.stderr.strip()})"
            )
        else:
            differ(fixtures / "spekkr" / "basic" / "expected", feature, "flags: default dir", failures)
        if (tmp_path / ".specify").exists():
            failures.append("flags: to-speckit wrote .specify without --activate")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        activated = run(
            codec_path,
            ["to-speckit", str(basic), "--dir", "specs/003-basic", "--activate"],
            cwd=tmp_path,
        )
        if activated.returncode != 0:
            failures.append(f"flags: --activate failed ({activated.stderr.strip()})")
        else:
            raw = (tmp_path / ".specify" / "feature.json").read_bytes()
            want = b'{"feature_directory":"specs/003-basic"}\n'
            if raw != want:
                failures.append(f"flags: feature.json is {raw!r}, want {want!r}")
            plan = tmp_path / "specs" / "003-basic" / "plan.md"
            if not plan.is_file() or plan.stat().st_size == 0:
                failures.append("flags: --activate did not leave a plan.md for Spec Kit to find")
            if b"feature_directory" not in raw:
                failures.append("flags: feature.json has no feature_directory")

    # An existing project keeps one .specify, even when --dir is not under specs/.
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        specify = tmp_path / ".specify"
        specify.mkdir()
        (specify / "feature.json").write_bytes(b'{"feature_directory":"specs/old"}\n')
        nested = run(
            codec_path,
            ["to-speckit", str(basic), "--dir", "features/basic", "--activate"],
            cwd=tmp_path,
        )
        if nested.returncode != 0:
            failures.append(f"flags: nested --activate failed ({nested.stderr.strip()})")
        else:
            raw = (specify / "feature.json").read_bytes()
            want = b'{"feature_directory":"features/basic"}\n'
            if raw != want:
                failures.append(f"flags: existing feature.json is {raw!r}, want {want!r}")
            if (tmp_path / "features" / ".specify").exists():
                failures.append("flags: --activate created features/.specify beside the feature")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        source = place(numbered, tmp_path / "in")
        default_back = run(
            codec_path,
            ["to-spekkr", str(source), "--author", "example-user", "--date", "2026-01-01"],
            cwd=tmp_path,
        )
        # The numbered folder 003-example becomes the slug "example".
        written = tmp_path / "example"
        if default_back.returncode != 0 or not (written / "spekkr.json").is_file():
            failures.append(
                f"flags: default Spekkr folder ./example was not written ({default_back.stderr.strip()})"
            )
        else:
            differ(numbered / "expected-spekkr", written, "flags: numbered default dir", failures)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        source = place(plain, tmp_path / "in")
        undated = run(
            codec_path,
            ["to-spekkr", str(source), "--dir", str(tmp_path / "out"), "--author", "example-user"],
        )
        if undated.returncode != 0:
            failures.append(f"flags: default date failed ({undated.stderr.strip()})")
        else:
            manifest = (tmp_path / "out" / "spekkr.json").read_text(encoding="utf-8")
            if '"date": "1970-01-01"' not in manifest:
                failures.append("flags: omitting --date did not use 1970-01-01")
            if "changelog date is 1970-01-01" not in undated.stderr:
                failures.append("flags: the default date was not reported on stderr")
            if "review it before publishing" not in undated.stderr:
                failures.append("flags: the filled-in summary was not reported on stderr")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        source = place(plain, tmp_path / "in")
        chosen = run(
            codec_path,
            [
                "to-spekkr",
                str(source),
                "--dir",
                str(tmp_path / "out"),
                "--author",
                "example-user",
                "--date",
                "2026-01-01",
                "--platforms",
                "cli, backend",
            ],
        )
        if chosen.returncode != 0:
            failures.append(f"flags: --platforms failed ({chosen.stderr.strip()})")
        else:
            manifest = json.loads((tmp_path / "out" / "spekkr.json").read_text(encoding="utf-8"))
            if manifest["targets"]["platforms"] != ["cli", "backend"]:
                failures.append(
                    "flags: --platforms was not applied: "
                    + json.dumps(manifest["targets"]["platforms"])
                )

    # The safety block the checker imports is the one the script writes.
    if not codec.SAFETY_BLOCK.startswith(codec.SAFETY_BEGIN):
        failures.append("flags: safety block does not start with its begin marker")
    if not codec.SAFETY_BLOCK.endswith(b"\n\n"):
        failures.append("flags: safety block does not end with a blank line")

    check_relative_source(codec_path, numbered, failures)
    check_unreadable_source(codec_path, basic, failures)


def check_relative_source(codec_path: Path, numbered: Path, failures: list[str]) -> None:
    """`.` and `..` name the directory they refer to, not the path text."""
    flags = ["--author", "example-user", "--date", "2026-01-01"]
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        source = place(numbered, tmp_path / "placed")
        dot = run(
            codec_path,
            ["to-spekkr", ".", "--dir", "../from-dot", *flags],
            cwd=source,
        )
        if not ok(dot, "flags", "to-spekkr .", failures):
            return
        differ(numbered / "expected-spekkr", source.parent / "from-dot", "flags: slug from .", failures)

        # `..` is the feature folder, and this empty child is part of that
        # tree, so only the derived id is compared with the golden manifest.
        inside = source / "inside"
        inside.mkdir()
        parent = run(
            codec_path,
            ["to-spekkr", "..", "--dir", "../../from-parent", *flags],
            cwd=inside,
        )
        if not ok(parent, "flags", "to-spekkr ..", failures):
            return
        written = source.parent / "from-parent" / "spekkr.json"
        if not written.is_file():
            failures.append("flags: to-spekkr .. did not write spekkr.json")
        else:
            spec_id = json.loads(written.read_text(encoding="utf-8"))["id"]
            if spec_id != "example-user/example":
                failures.append(f"flags: slug from .. is {spec_id!r}")


def check_unreadable_source(codec_path: Path, basic: Path, failures: list[str]) -> None:
    """An unreadable subdirectory aborts the conversion and writes nothing."""
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        source = tmp_path / "spec"
        shutil.copytree(basic, source)
        hidden = source / "reference"
        hidden.mkdir()
        (hidden / "note.md").write_text("hidden\n", encoding="utf-8")
        hidden.chmod(0)
        out = tmp_path / "out"
        try:
            proc = run(codec_path, ["to-speckit", str(source), "--dir", str(out)])
        finally:
            hidden.chmod(0o755)
    if proc.returncode == 0:
        failures.append("flags: an unreadable directory was converted")
        return
    if not proc.stderr.startswith("error: cannot read "):
        failures.append(f"flags: unreadable directory stderr was {proc.stderr!r}")
    if proc.stdout:
        failures.append(f"flags: an unreadable directory wrote to stdout: {proc.stdout!r}")
    if out.exists():
        failures.append("flags: an unreadable directory left an output folder")


def cases(root: Path) -> list[Path]:
    return sorted(path for path in root.iterdir() if path.is_dir())


def place(case: Path, dest: Path) -> Path:
    """Copy source/ to a folder of the name the codec should see."""
    name = case.name
    marker = case / "folder-name"
    if marker.is_file():
        name = marker.read_text(encoding="utf-8").strip()
    dest.mkdir(parents=True)
    target = dest / name
    shutil.copytree(case / "source", target)
    return target


def run(
    codec: Path,
    args: list[str],
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(codec), *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def ok(proc: subprocess.CompletedProcess[str], label: str, step: str, failures: list[str]) -> bool:
    if proc.returncode == 0:
        return True
    failures.append(f"{label}: {step} exited {proc.returncode}: {proc.stderr.strip()}")
    return False


def expect_error(
    codec: Path,
    args: list[str],
    case: Path,
    label: str,
    failures: list[str],
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rewritten: list[str] = []
        index = 0
        while index < len(args):
            if (
                args[index] == "--dir"
                and index + 1 < len(args)
                and not Path(args[index + 1]).is_absolute()
            ):
                rewritten.extend(["--dir", str(tmp_path / args[index + 1])])
                index += 2
                continue
            rewritten.append(args[index])
            index += 1
        proc = run(codec, rewritten)
    want = (case / "error.txt").read_text(encoding="utf-8")
    if not want.endswith("\n"):
        want += "\n"
    if proc.returncode == 0:
        failures.append(f"{label}: expected a failure, but the command succeeded")
        return
    if proc.stderr != want:
        failures.append(f"{label}: stderr {proc.stderr!r}, want {want!r}")
    if proc.stdout:
        failures.append(f"{label}: a failure wrote to stdout: {proc.stdout!r}")


def assert_safety(codec, source: Path, feature: Path, label: str, failures: list[str]) -> None:
    plan = (feature / "plan.md").read_bytes()
    design = (source / "design.md").read_bytes()
    stub = (feature / "design.md").read_bytes()
    if stub != codec.DESIGN_STUB:
        failures.append(f"{label}: design.md stub is not the codec's stub")
    if not plan.startswith(codec.SAFETY_BLOCK):
        failures.append(f"{label}: plan.md does not start with the safety block")
    elif plan[len(codec.SAFETY_BLOCK) :] != design:
        failures.append(f"{label}: removing the safety block does not restore design.md")


def differ(left: Path, right: Path, label: str, failures: list[str]) -> None:
    if not left.exists() or not right.exists():
        failures.append(f"{label}: missing {left} or {right}")
        return
    left_files, left_dirs = snapshot(left)
    right_files, right_dirs = snapshot(right)
    if left_files.keys() != right_files.keys() or left_dirs != right_dirs:
        missing = sorted((set(left_files) | left_dirs) - (set(right_files) | right_dirs))
        extra = sorted((set(right_files) | right_dirs) - (set(left_files) | left_dirs))
        detail = []
        if missing:
            detail.append("missing " + ", ".join(missing))
        if extra:
            detail.append("extra " + ", ".join(extra))
        failures.append(f"{label}: tree differs ({'; '.join(detail)})")
        return
    for rel, data in left_files.items():
        other = right_files[rel]
        if data != other:
            offset = next((i for i, (a, b) in enumerate(zip(data, other)) if a != b), min(len(data), len(other)))
            failures.append(
                f"{label}: {rel} differs at byte {offset} "
                f"({len(data)} bytes vs {len(other)} bytes)"
            )
            return


def snapshot(root: Path) -> tuple[dict[str, bytes], set[str]]:
    files: dict[str, bytes] = {}
    directories: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        for name in dirnames:
            rel = (current / name).relative_to(root).as_posix()
            directories.add(rel + "/")
        for name in filenames:
            path = current / name
            rel = path.relative_to(root).as_posix()
            files[rel] = path.read_bytes()
    return files, directories


if __name__ == "__main__":
    sys.exit(main())
