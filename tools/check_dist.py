"""Build-artifact acceptance in a clean environment outside the source tree."""

# SPDX-License-Identifier: Apache-2.0
import argparse
import email
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tarfile
import tempfile
import venv
import zipfile


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist-dir", type=Path, default=root / "dist")
    args = parser.parse_args()
    wheels = list(args.dist_dir.resolve().glob("*.whl"))
    archives = list(args.dist_dir.resolve().glob("*.tar.gz"))
    assert len(wheels) == len(archives) == 1, "dist must contain one wheel and one sdist"
    wheel, archive = wheels[0], archives[0]
    with zipfile.ZipFile(wheel) as package:
        names = package.namelist()
        for module in ("core", "contracts"):
            assert f"nymph_toolkit/{module}/__init__.py" in names
        assert "nymph_toolkit/core/runtime.py" in names
        assert "nymph_toolkit/core/registry.py" in names
        assert "nymph_toolkit/core/module_group.py" in names
        assert "nymph_toolkit/contracts/registry.py" in names
        for path in ("core/connections.py", "core/storage.py", "core/_storage_io.py", "contracts/connections.py",
                     "core/task_manager.py", "core/_activity_history.py", "contracts/activities.py",
                     "core/_activity_commands.py", "core/_activity_slots.py", "core/hybrid.py",
                     "core/hybrid_tasks.py", "core/_child.py", "core/_streams.py", "contracts/hybrid.py",
                     "contracts/modules.py", "core/_module_contract.py"):
            assert "nymph_toolkit/" + path in names
        metadata_path = next(n for n in names if n.endswith(".dist-info/METADATA"))
        metadata = email.message_from_bytes(package.read(metadata_path))
        assert metadata["Name"] == "nymph-toolkit"
        assert metadata["Version"] == "1.0.0"
        assert metadata["Requires-Python"] == ">=3.12"
        assert metadata["License-Expression"] == "Apache-2.0"
        assert metadata.get_all("Requires-Dist", []) == []
        license_path = next(n for n in names if n.endswith(".dist-info/licenses/LICENSE"))
        assert package.read(license_path) == (root / "LICENSE").read_bytes()
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    with tempfile.TemporaryDirectory(prefix="ntk-dist-") as temporary:
        work = Path(temporary)
        environment = work / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run(
            [str(python), "-m", "pip", "install", "--no-deps", "--no-index", str(wheel)],
            cwd=work, env=env, check=True,
        )
        probe = (
            "from pathlib import Path; import nymph_toolkit.core as core; from nymph_toolkit.core import Runtime, Registry, ModuleGroup, Connections, FileStore, TaskManager; "
            "from nymph_toolkit.contracts import RuntimeService, RuntimeState, ModuleSpec, ModuleKind, BindingKey, ContractKey, StorageFailure, ActivityRequest, ActivityHistory, ActivityChange, ActivityCommandStatus, ActivityControlKind, UNCHANGED; "
            "from importlib.metadata import version; import sys; "
            "assert version('nymph-toolkit') == '1.0.0'; "
            "assert Path(core.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()); "
            "assert RuntimeState.NEW.value == 'new'; print('installed imports: PASS')"
        )
        subprocess.run([str(python), "-I", "-c", probe], cwd=work, env=env, check=True)
        example = root / "examples" / "runtime_demo.py"
        assert example.is_file(), "The runtime acceptance example is required"
        subprocess.run([str(python), "-I", str(example)], cwd=work, env=env, check=True)
        registry_example = root / "examples" / "registry_demo.py"
        assert registry_example.is_file(), "The Registry acceptance example is required"
        subprocess.run([str(python), "-I", str(registry_example)], cwd=work, env=env, check=True)
        connections_example = root / "examples" / "connections_demo.py"
        assert connections_example.is_file(), "The Connections acceptance example is required"
        subprocess.run([str(python), "-I", str(connections_example)], cwd=work, env=env, check=True)
        activity_example = root / "examples" / "task_manager_demo.py"
        assert activity_example.is_file(), "The TaskManager acceptance example is required"
        subprocess.run([str(python), "-I", str(activity_example)], cwd=work, env=env, check=True)
        changes_example = root / "examples" / "activity_changes_demo.py"
        assert changes_example.is_file(), "The v0.6 activity changes example is required"
        subprocess.run([str(python), "-I", str(changes_example)], cwd=work, env=env, check=True)
        # Only fixtures are copied, so child factories are importable from this
        # external working directory without exposing the checkout's src tree.
        shutil.copytree(root / "tests", work / "tests", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(root / "examples", work / "examples", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(root / "tools", work / "tools", ignore=shutil.ignore_patterns("__pycache__"))
        (work / "docs").mkdir()
        shutil.copyfile(root / "docs/api-reference.md", work / "docs/api-reference.md")
        shutil.copyfile(root / "docs/contracts-v1.json", work / "docs/contracts-v1.json")
        subprocess.run([str(python), "-I", str(work / "tools/check_api.py")], cwd=work, env=env, check=True)
        subprocess.run([str(python), "-I", str(work / "tools/check_contracts.py")], cwd=work, env=env, check=True)
        subprocess.run([str(python), "-I", str(work / "examples/hybrid_demo.py")], cwd=work, env=env, check=True)
        subprocess.run([str(python), "-I", str(work / "examples/module_contract_demo.py")], cwd=work, env=env, check=True)
        subprocess.run(
            [str(python), "-I", "-W", "error", "-m", "unittest", "discover",
             "-s", str(work / "tests"), "-t", str(work), "-v"],
            cwd=work, env=env, check=True,
        )
        subprocess.run([str(python), "-I", "-W", "error", str(work / "tools/validate_hybrid_load.py"),
                        "--duration", "1", "--requests", "8", "--chunks", "4", "--cycle-requests", "4",
                        "--cycle-chunks", "2", "--sample-interval", "1", "--output", str(work / "load.json")],
                       cwd=work, env=env, check=True)
        source = work / "source"
        source.mkdir()
        with tarfile.open(archive) as package:
            package.extractall(source, filter="data")
        directories = list(source.iterdir())
        assert len(directories) == 1 and directories[0].is_dir()
        assert (directories[0] / "LICENSE").read_bytes() == (root / "LICENSE").read_bytes()
        rebuilt = work / "rebuilt"
        subprocess.run(
            [sys.executable, "-m", "build", "--wheel", "--outdir", str(rebuilt), str(directories[0])],
            cwd=work, env=env, check=True,
        )
        rebuilt_wheel = next(rebuilt.glob("*.whl"))
        assert rebuilt_wheel.read_bytes() == wheel.read_bytes(), "sdist must rebuild the same wheel"
    print("PASS: wheel metadata, LICENSE, isolated installation, sdist rebuild")


if __name__ == "__main__":
    main()
