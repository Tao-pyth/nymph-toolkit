"""Build-artifact acceptance in a clean environment outside the source tree."""

# SPDX-License-Identifier: Apache-2.0
import email
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    wheels = list((root / "dist").glob("*.whl"))
    archives = list((root / "dist").glob("*.tar.gz"))
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
        metadata_path = next(n for n in names if n.endswith(".dist-info/METADATA"))
        metadata = email.message_from_bytes(package.read(metadata_path))
        assert metadata["Name"] == "nymph-toolkit"
        assert metadata["Version"] == "0.3.0"
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
            "from pathlib import Path; import nymph_toolkit.core as core; from nymph_toolkit.core import Runtime, Registry, ModuleGroup; "
            "from nymph_toolkit.contracts import RuntimeService, RuntimeState, ModuleSpec, ModuleKind; "
            "from importlib.metadata import version; import sys; "
            "assert version('nymph-toolkit') == '0.3.0'; "
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
        subprocess.run(
            [str(python), "-I", "-W", "error", "-m", "unittest", "discover",
             "-s", str(root / "tests"), "-t", str(root), "-v"],
            cwd=work, env=env, check=True,
        )
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
