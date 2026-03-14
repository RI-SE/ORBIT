"""Generate maintainability metrics for ORBIT source code."""

from __future__ import annotations

import argparse
import ast
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FunctionMetric:
    """Represents a function-length metric entry."""

    lines: int
    file: str
    lineno: int
    name: str


@dataclass(frozen=True)
class CoverageMetric:
    """Represents a file-level coverage metric entry."""

    missing_lines: int
    coverage_percent: float
    file: str
    covered_statements: int
    total_statements: int


def python_files(root: Path) -> list[Path]:
    """Collect Python files under the provided root."""
    return sorted(path for path in root.rglob("*.py") if path.is_file())


def top_largest_files(paths: list[Path], root: Path, limit: int) -> list[tuple[int, str]]:
    """Return largest files by line count."""
    entries: list[tuple[int, str]] = []
    for path in paths:
        line_count = sum(1 for _ in path.open("r", encoding="utf-8"))
        entries.append((line_count, str(path.relative_to(root))))
    entries.sort(reverse=True)
    return entries[:limit]


def top_long_functions(paths: list[Path], root: Path, threshold: int, limit: int) -> tuple[int, list[FunctionMetric]]:
    """Return long functions and the total count above the threshold."""
    long_functions: list[FunctionMetric] = []
    for path in paths:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or not hasattr(node, "end_lineno"):
                continue
            line_span = node.end_lineno - node.lineno + 1
            if line_span <= threshold:
                continue
            long_functions.append(
                FunctionMetric(
                    lines=line_span,
                    file=str(path.relative_to(root)),
                    lineno=node.lineno,
                    name=node.name,
                )
            )
    long_functions.sort(key=lambda item: item.lines, reverse=True)
    return len(long_functions), long_functions[:limit]


def read_coverage_metrics(coverage_json: Path) -> list[CoverageMetric]:
    """Parse coverage.py JSON output into sortable file metrics."""
    payload = json.loads(coverage_json.read_text(encoding="utf-8"))
    metrics: list[CoverageMetric] = []
    for file_path, details in payload.get("files", {}).items():
        if not file_path.startswith("orbit/"):
            continue
        summary = details.get("summary", {})
        total = int(summary.get("num_statements", 0))
        missing = int(summary.get("missing_lines", 0))
        if total == 0:
            continue
        covered = total - missing
        coverage = covered / total * 100
        metrics.append(
            CoverageMetric(
                missing_lines=missing,
                coverage_percent=coverage,
                file=file_path,
                covered_statements=covered,
                total_statements=total,
            )
        )
    metrics.sort(key=lambda item: item.missing_lines, reverse=True)
    return metrics


def print_header(title: str) -> None:
    """Print a compact section header."""
    print(f"\n{title}")
    print("-" * len(title))


def main() -> int:
    """Run the maintainability report CLI."""
    parser = argparse.ArgumentParser(description="Generate ORBIT maintainability report.")
    parser.add_argument("--root", type=Path, default=Path("."), help="Repository root path.")
    parser.add_argument("--source-dir", type=Path, default=Path("orbit"), help="Source directory to analyze.")
    parser.add_argument("--coverage-json", type=Path, help="Path to coverage JSON report from pytest-cov.")
    parser.add_argument("--top-files", type=int, default=15, help="Number of largest files to show.")
    parser.add_argument("--top-functions", type=int, default=20, help="Number of longest functions to show.")
    parser.add_argument("--function-threshold", type=int, default=80, help="Line threshold for long functions.")
    args = parser.parse_args()

    repo_root = args.root.resolve()
    source_root = (repo_root / args.source_dir).resolve()
    files = python_files(source_root)

    print("ORBIT maintainability report")
    print(f"Analyzed files: {len(files)}")
    print(f"Source root: {source_root.relative_to(repo_root)}")

    print_header("Largest Python files")
    for lines, file_path in top_largest_files(files, repo_root, args.top_files):
        print(f"{lines:5d}  {file_path}")

    total_long, longest = top_long_functions(files, repo_root, args.function_threshold, args.top_functions)
    print_header(f"Functions longer than {args.function_threshold} lines: {total_long}")
    for metric in longest:
        print(f"{metric.lines:4d}  {metric.file}:{metric.lineno}  {metric.name}")

    if args.coverage_json:
        coverage_path = args.coverage_json
        if not coverage_path.is_absolute():
            coverage_path = (repo_root / coverage_path).resolve()
        if not coverage_path.exists():
            print_header("Coverage")
            print(f"Coverage JSON not found: {coverage_path}")
            return 0

        coverage_metrics = read_coverage_metrics(coverage_path)
        print_header("Top uncovered files")
        for metric in coverage_metrics[:15]:
            print(
                f"{metric.missing_lines:4d} missing  "
                f"{metric.coverage_percent:5.1f}%  "
                f"{metric.file} ({metric.covered_statements}/{metric.total_statements})"
            )

        print_header("Top uncovered non-GUI files")
        non_gui = [metric for metric in coverage_metrics if "/gui/" not in metric.file]
        for metric in non_gui[:15]:
            print(
                f"{metric.missing_lines:4d} missing  "
                f"{metric.coverage_percent:5.1f}%  "
                f"{metric.file} ({metric.covered_statements}/{metric.total_statements})"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
