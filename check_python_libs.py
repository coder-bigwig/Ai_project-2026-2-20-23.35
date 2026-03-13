#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import json
import sys
from dataclasses import asdict, dataclass
from importlib import metadata
from typing import Iterable, List, Optional


@dataclass(frozen=True)
class LibrarySpec:
    display_name: str
    module_name: str
    package_name: str


@dataclass
class CheckResult:
    display_name: str
    module_name: str
    package_name: str
    status: str
    version: str
    location: str
    error: str


DEFAULT_LIBRARIES: List[LibrarySpec] = [
    LibrarySpec("NumPy", "numpy", "numpy"),
    LibrarySpec("Pandas", "pandas", "pandas"),
    LibrarySpec("Matplotlib", "matplotlib", "matplotlib"),
    LibrarySpec("Scikit-learn", "sklearn", "scikit-learn"),
    LibrarySpec("Pillow", "PIL", "Pillow"),
    LibrarySpec("OpenCV", "cv2", "opencv-python"),
    LibrarySpec("PyTorch", "torch", "torch"),
    LibrarySpec("TorchVision", "torchvision", "torchvision"),
    LibrarySpec("UltraLytics", "ultralytics", "ultralytics"),
    LibrarySpec("Transformers", "transformers", "transformers"),
    LibrarySpec("Accelerate", "accelerate", "accelerate"),
    LibrarySpec("Timm", "timm", "timm"),
    LibrarySpec("SentencePiece", "sentencepiece", "sentencepiece"),
    LibrarySpec("TensorFlow", "tensorflow", "tensorflow-cpu"),
]


def parse_extra_specs(extra_values: Iterable[str]) -> List[LibrarySpec]:
    extras: List[LibrarySpec] = []
    for raw in extra_values:
        if not raw.strip():
            continue
        if ":" in raw:
            module_name, package_name = raw.split(":", 1)
            module_name = module_name.strip()
            package_name = package_name.strip()
        else:
            module_name = raw.strip()
            package_name = module_name

        if not module_name:
            raise ValueError(f"Invalid --extra value: {raw!r}")

        extras.append(
            LibrarySpec(
                display_name=module_name,
                module_name=module_name,
                package_name=package_name or module_name,
            )
        )
    return extras


def resolve_version(spec: LibrarySpec, module_obj: object) -> str:
    try:
        return metadata.version(spec.package_name)
    except metadata.PackageNotFoundError:
        pass
    except Exception:
        pass

    version_value = getattr(module_obj, "__version__", None)
    if version_value is None:
        return "-"
    return str(version_value)


def check_library(spec: LibrarySpec) -> CheckResult:
    try:
        module_obj = importlib.import_module(spec.module_name)
        version = resolve_version(spec, module_obj)
        location = getattr(module_obj, "__file__", "built-in") or "built-in"
        return CheckResult(
            display_name=spec.display_name,
            module_name=spec.module_name,
            package_name=spec.package_name,
            status="OK",
            version=version,
            location=str(location),
            error="",
        )
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            display_name=spec.display_name,
            module_name=spec.module_name,
            package_name=spec.package_name,
            status="MISSING",
            version="-",
            location="-",
            error=f"{exc.__class__.__name__}: {exc}",
        )


def print_table(results: List[CheckResult]) -> None:
    headers = ["Library", "Module", "Package", "Status", "Version", "Location"]
    rows = [
        [
            r.display_name,
            r.module_name,
            r.package_name,
            r.status,
            r.version,
            r.location,
        ]
        for r in results
    ]

    widths = [len(h) for h in headers]
    for row in rows:
        for i, col in enumerate(row):
            widths[i] = max(widths[i], len(str(col)))

    def format_row(columns: List[str]) -> str:
        return " | ".join(str(col).ljust(widths[i]) for i, col in enumerate(columns))

    line = "-+-".join("-" * w for w in widths)
    print(format_row(headers))
    print(line)
    for row in rows:
        print(format_row(row))

    missing = [r for r in results if r.status != "OK"]
    print()
    print(f"Total: {len(results)}; OK: {len(results) - len(missing)}; Missing: {len(missing)}")
    if missing:
        print("Missing details:")
        for item in missing:
            print(f"- {item.display_name} ({item.module_name}): {item.error}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check whether required Python libraries are installed."
    )
    parser.add_argument(
        "--extra",
        action="append",
        default=[],
        help="Extra module check in format 'module' or 'module:package'.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON output.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero if any library is missing.",
    )
    args = parser.parse_args()

    specs = list(DEFAULT_LIBRARIES) + parse_extra_specs(args.extra)
    results = [check_library(spec) for spec in specs]

    if args.json:
        print(
            json.dumps(
                [asdict(r) for r in results],
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print_table(results)

    if args.strict and any(r.status != "OK" for r in results):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
