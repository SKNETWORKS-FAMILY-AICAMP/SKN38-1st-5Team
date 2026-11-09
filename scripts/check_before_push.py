#!/usr/bin/env python3
"""공개 전 검사. Git 명령을 실행하지 않으며 발견한 값 대신 위치만 출력한다.

저장소에서는 index의 추적 파일(무시 규칙과 무관)과 새로 추가할 수 있는 파일을
검사한다. 저장소가 없으면 중첩 .gitignore까지 적용한다. 커밋 이력 검사기는 아니다.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import fnmatch
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import struct
import sys
import tomllib


@dataclass(frozen=True, order=True)
class Finding:
    path: str
    line: int
    reason: str


def forbidden_path(path: str) -> bool:
    parts = PurePosixPath(path).parts
    name = parts[-1].lower()
    if any(part in {"work", "prototypes", ".venv"} for part in parts):
        return True
    if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
        return True
    if name == "secrets.toml" or name.endswith(".sql.gz"):
        return True
    return any(parts[i:i + 2] == ("data", "raw") or
               (parts[i:i + 2] == ("data", "processed") and name.endswith(".csv"))
               for i in range(len(parts) - 1))


def _glob_regex(pattern: str) -> str:
    result, i = "", 0
    while i < len(pattern):
        char = pattern[i]
        if char == "\\" and i + 1 < len(pattern):
            i += 1
            result += re.escape(pattern[i])
        elif pattern[i:i + 3] == "**/":
            result += "(?:[^/]+/)*"
            i += 2
        elif pattern[i:i + 2] == "**":
            result += ".*"
            i += 1
        elif char == "*":
            result += "[^/]*"
        elif char == "?":
            result += "[^/]"
        elif char == "[" and "]" in pattern[i + 1:]:
            end = pattern.index("]", i + 1)
            translated = fnmatch.translate(pattern[i:end + 1])
            result += translated[4:translated.rfind(")")]
            i = end
        else:
            result += re.escape(char)
        i += 1
    return result


@dataclass(frozen=True)
class IgnoreRule:
    base: str
    expression: re.Pattern[str]
    negated: bool
    directory_only: bool

    def matches(self, path: str, is_directory: bool) -> bool:
        if self.base and not path.startswith(self.base):
            return False
        return (not self.directory_only or is_directory) and bool(
            self.expression.fullmatch(path[len(self.base):]))


def _ignore_rules(path: Path, root: Path) -> list[IgnoreRule]:
    if not path.is_file() or path.is_symlink():
        return []
    base = path.parent.relative_to(root).as_posix()
    base = "" if base == "." else base + "/"
    rules = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = re.sub(r"(?<!\\) +$", "", raw)
        if not line or line.startswith("#"):
            continue
        negated = line.startswith("!")
        if negated:
            line = line[1:]
        directory_only = line.endswith("/")
        line = line.rstrip("/")
        anchored = line.startswith("/") or "/" in line
        pattern = _glob_regex(line.lstrip("/"))
        rules.append(IgnoreRule(base, re.compile(("" if anchored else "(?:.*/)?") + pattern),
                                negated, directory_only))
    return rules


def worktree_files(root: Path) -> set[str]:
    files: set[str] = set()

    def visit(directory: Path, inherited: list[IgnoreRule]) -> None:
        rules = inherited + _ignore_rules(directory / ".gitignore", root)
        for child in sorted(directory.iterdir()):
            if child.name == ".git":
                continue
            relative = child.relative_to(root).as_posix()
            is_directory = child.is_dir() and not child.is_symlink()
            ignored = False
            for rule in rules:
                if rule.matches(relative, is_directory):
                    ignored = not rule.negated
            if ignored:
                continue
            if is_directory:
                visit(child, rules)
            else:
                files.add(relative)

    visit(root, [])
    return files


def tracked_files(root: Path) -> set[str]:
    git_dir = root / ".git"
    if not git_dir.exists():
        return set()
    if git_dir.is_file():
        pointer = git_dir.read_text(encoding="utf-8").strip()
        if not pointer.startswith("gitdir: "):
            raise ValueError("index")
        git_dir = (root / pointer[8:]).resolve()
    index = git_dir / "index"
    if not index.exists():
        if (git_dir / "HEAD").exists():
            # index가 사라진 기존 저장소를 빈 저장소로 오인하지 않는다.
            raise ValueError("index")
        return set()
    data = index.read_bytes()
    signature, version, count = struct.unpack_from("!4sII", data)
    if signature != b"DIRC" or version not in (2, 3, 4):
        raise ValueError("index")
    hash_size = next((size for size, digest in ((20, hashlib.sha1), (32, hashlib.sha256))
                      if len(data) >= size and digest(data[:-size]).digest() == data[-size:]), None)
    if hash_size is None:
        raise ValueError("index")
    pos, previous, paths = 12, b"", set()
    for _ in range(count):
        start = pos
        flags = struct.unpack_from("!H", data, pos + 40 + hash_size)[0]
        pos += 42 + hash_size
        if flags & 0x4000:
            if version == 2:
                raise ValueError("index")
            pos += 2
        if version == 4:
            byte = data[pos]
            pos += 1
            remove = byte & 0x7f
            while byte & 0x80:
                byte = data[pos]
                pos += 1
                remove = ((remove + 1) << 7) | (byte & 0x7f)
            if remove > len(previous):
                raise ValueError("index")
            prefix = previous[:len(previous) - remove]
        else:
            prefix = b""
        end = data.index(b"\0", pos)
        previous = prefix + data[pos:end]
        name = os.fsdecode(previous)
        if not name or name.startswith("/") or ".." in PurePosixPath(name).parts:
            raise ValueError("index")
        paths.add(name)
        pos = end + 1 if version == 4 else start + ((end + 1 - start + 7) // 8) * 8
    while pos < len(data) - hash_size:
        extension, size = struct.unpack_from("!4sI", data, pos)
        if not 65 <= extension[0] <= 90:  # split/sparse 등 필수 확장은 실패 처리한다.
            raise ValueError("index")
        pos += 8 + size
    if pos != len(data) - hash_size:
        raise ValueError("index")
    return paths


SECRET_NAME = r"(?:password|passwd|pwd|[\w-]*api[_-]?key|service[_-]?key|[\w-]*token|[\w-]*secret)"
ASSIGNMENT = re.compile(
    rf"(?i)\b{SECRET_NAME}\b[\"']?\s*(?::|=(?!=))\s*(?:([\"'])([^\r\n]*?)\1|([^\s,;}})\]]+))")
ANTHROPIC_KEY = re.compile(r"sk-ant-[A-Za-z0-9_-]{12,}")
LONG_KEY = re.compile(r"(?<![\w+/%=-])(?:[0-9a-fA-F]{64,128}|[A-Za-z0-9+/%]{80,128}={0,2})(?![\w+/%=-])")
PLACEHOLDERS = {"", "...", "none", "null", "example", "test-only", "environment-only",
                "test", "dummy", "changeme", "change-me", "replace-me", "password", "{}", "[]"}
EXAMPLE_MARKERS = ("fake", "fixture", "dummy", "omit", "example", "test", "changeme")


def _placeholder(value: str) -> bool:
    value = value.strip().lower()
    # 예제값 예외는 이름 기반 검사에만 적용하며 실제 키 패턴은 별도로 검사한다.
    return (len(value) < 16 or any(marker in value for marker in EXAMPLE_MARKERS)
            or value in PLACEHOLDERS or value.startswith(("your_", "your-", "<", "${", "example-"))
            or set(value) <= {"x", "*"})


def _private_values(root: Path) -> set[str]:
    values: set[str] = set()

    def collect(value: object, key: str = "") -> None:
        if isinstance(value, dict):
            for name, child in value.items():
                collect(child, str(name))
        elif re.fullmatch(SECRET_NAME, key, re.I) and isinstance(value, str) and value.strip():
            # 로컬 비밀값에는 예제값 예외를 적용하지 않는다.
            values.add(value)

    for path in (root / ".streamlit/secrets.toml", root / "secrets.toml"):
        if path.is_file() and not path.is_symlink():
            collect(tomllib.loads(path.read_text(encoding="utf-8")))
    return values


def content_findings(path: str, body: str, known_values: set[str]) -> list[Finding]:
    findings = []
    checksum_values: set[str] = set()

    def collect_checksums(value: object, checksum: bool = False) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                collect_checksums(child, checksum or bool(re.search(r"sha[_-]?256|checksum", key, re.I)))
        elif isinstance(value, str) and checksum and re.fullmatch(r"[a-fA-F0-9]{64}", value):
            checksum_values.add(value)

    if path.endswith(".json"):
        try:
            collect_checksums(json.loads(body))
        except (ValueError, TypeError):
            pass
    private_patterns = [re.compile(r"(?<!\w)" + re.escape(value) + r"(?!\w)") for value in known_values]
    for number, line in enumerate(body.splitlines(), 1):
        reasons = set()
        if ANTHROPIC_KEY.search(line):
            reasons.add("API 키 패턴")
        if re.search(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----", line):
            reasons.add("개인 키 패턴")
        if any(pattern.search(line) for pattern in private_patterns):
            reasons.add("로컬 비밀값과 일치")
        for match in ASSIGNMENT.finditer(line):
            quoted, literal, bare = match.groups()
            value = literal if quoted else bare
            if not quoted and path.endswith(".py") and (value.startswith(("{", "[", "(")) or
                    re.match(r"[A-Za-z_]\w*(?:[.(\[]|$)", value)):
                continue  # 변수 참조는 비밀값의 직접 지정이 아니다.
            if not _placeholder(value):
                reasons.add("비밀값 직접 지정")
        # 잠금 파일의 공개 패키지 해시는 비밀 키가 아니다.
        for match in LONG_KEY.finditer(line):
            value = match.group()
            prefix = line[max(0, match.start() - 18):match.start()].lower()
            if value in checksum_values or re.search(r"sha(?:256|512)[\"']?[:=]\s*[\"']?$", prefix):
                continue
            if (path.endswith(".md") and re.fullmatch(r"[a-fA-F0-9]{64}", value)
                    and re.search(r"sha[ -]?256", body, re.I)
                    and re.search(r"\.(?:csv|json|xlsx|geojson|html|xml|txt|zip)\b", line)):
                continue
            if not re.fullmatch(r"[a-fA-F0-9]{64,128}", value) and not all(
                    re.search(pattern, value) for pattern in (r"[a-z]", r"[A-Z]", r"\d")):
                continue
            reasons.add("긴 API 키 후보")
        findings.extend(Finding(path, number, reason) for reason in sorted(reasons))
    return findings


def scan(root: Path) -> list[Finding]:
    root = root.resolve()
    try:
        candidates = tracked_files(root) | worktree_files(root)
        known_values = _private_values(root)
    except (OSError, ValueError, IndexError, struct.error, re.error):
        return [Finding(".git/index / .gitignore / secrets.toml", 0, "검사 입력을 읽을 수 없음")]
    findings = []
    for relative in sorted(candidates):
        path = root / relative
        if forbidden_path(relative):
            findings.append(Finding(relative, 0, "공개 금지 경로"))
            continue
        try:
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                findings.append(Finding(relative, 0, "심볼릭 링크 별도 확인 필요"))
                continue
            if not path.is_file():
                findings.append(Finding(relative, 0, "추적 파일을 읽을 수 없음"))
                continue
            body = path.read_bytes()
            if b"\0" in body[:8192]:
                continue
            findings.extend(content_findings(relative, body.decode("utf-8", errors="replace"), known_values))
        except OSError:
            findings.append(Finding(relative, 0, "파일을 읽을 수 없음"))
    return sorted(set(findings))


def ignored_forbidden(root: Path) -> Counter[str]:
    root = root.resolve()
    candidates = tracked_files(root) | worktree_files(root)
    counts: Counter[str] = Counter()
    for folder, directories, names in os.walk(root):
        if ".git" in directories:
            directories.remove(".git")
        for name in names:
            relative = (Path(folder) / name).relative_to(root).as_posix()
            if relative not in candidates and forbidden_path(relative):
                counts[relative.split("/", 1)[0]] += 1
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    findings = scan(args.root)
    for finding in findings:
        location = f"{finding.path}:{finding.line}" if finding.line else finding.path
        print(f"{location} [{finding.reason}]")
    if findings:
        print(f"공개 전 검사: {len(findings)}건 확인 필요")
        return 1
    print("공개 전 검사: 통과 (git으로 올라갈 파일 기준)")
    ignored = ignored_forbidden(args.root)
    if ignored:
        print(f"참고: .gitignore로 빠진 공개 금지 파일 {sum(ignored.values()):,}개 ({', '.join(sorted(ignored))})")
        print("GitHub 웹 화면에 폴더를 끌어다 올리면 .gitignore가 적용되지 않아요. git으로만 올려 주세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
