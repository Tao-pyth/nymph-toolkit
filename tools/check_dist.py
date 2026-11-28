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
                     "contracts/modules.py", "core/_module_contract.py", "contracts/memory.py",
                     "subsystems/memory/__init__.py", "subsystems/memory/_store.py", "subsystems/memory/_records.py",
                     "contracts/cognition.py", "subsystems/cognition/__init__.py",
                     "subsystems/cognition/_store.py", "subsystems/cognition/_model.py",
                     "contracts/cognition_revision.py", "contracts/text_interaction.py", "contracts/web.py",
                     "adapters/_interaction.py", "adapters/text_interaction/__init__.py",
                     "adapters/web/__init__.py", "adapters/web/_reader.py", "contracts/agency.py",
                     "subsystems/agency/__init__.py", "subsystems/agency/_model.py", "subsystems/agency/_store.py", "subsystems/agency/_execution.py", "contracts/persona.py", "subsystems/persona/__init__.py", "subsystems/persona/_model.py", "subsystems/persona/_store.py", "contracts/sleep.py", "subsystems/sleep/__init__.py", "subsystems/sleep/_model.py", "subsystems/sleep/_store.py"):
            assert "nymph_toolkit/" + path in names
        for path in ("contracts/sleep_activity.py", "contracts/voice.py", "subsystems/sleep_activity/__init__.py",
                     "subsystems/sleep_activity/_store.py", "subsystems/sleep_activity/_model.py",
                     "adapters/discord_voice/__init__.py", "adapters/discord_voice/_audio.py",
                     "adapters/discord_voice/_model.py", "adapters/discord_voice/_session.py",
                     "adapters/discord_voice/_model_files.py", "adapters/discord_voice/model-files.json",
                     "adapters/discord_voice/bridge.mjs", "adapters/discord_voice/node/package.json",
                     "adapters/discord_voice/node/pnpm-lock.yaml"):
            assert "nymph_toolkit/" + path in names
        for path in ("contracts/input_candidate.py", "contracts/_memory_record.py", "adapters/input_candidate/__init__.py"):
            assert "nymph_toolkit/" + path in names
        for path in ("contracts/diagnostics.py", "diagnostics/__init__.py", "diagnostics/_session.py",
                     "diagnostics/_viewer.py", "diagnostics/_publisher.py",
                     "diagnostics/viewer.css", "diagnostics/viewer.html", "diagnostics/viewer.js"):
            assert "nymph_toolkit/" + path in names
        assert not any("node_modules/" in name for name in names)
        metadata_path = next(n for n in names if n.endswith(".dist-info/METADATA"))
        metadata = email.message_from_bytes(package.read(metadata_path))
        assert metadata["Name"] == "nymph-toolkit"
        assert metadata["Version"] == "1.12.0"
        assert metadata["Requires-Python"] == ">=3.12"
        assert metadata["License-Expression"] == "Apache-2.0"
        requirements = metadata.get_all("Requires-Dist", [])
        assert len(requirements) == 1 and requirements[0].split(";")[0].strip() == "vosk==0.3.45"
        assert requirements[0].split(";")[1].strip().replace("'", '"') == 'extra == "voice"'
        assert metadata.get_all("Provides-Extra") == ["voice"]
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
            "from nymph_toolkit.subsystems.memory import factory; from nymph_toolkit.contracts.memory import MEMORY_CONTRACT; "
            "import sys; import nymph_toolkit.adapters.document as document; from nymph_toolkit.contracts.document import DOCUMENT_CONTRACT; "
            "assert Path(document.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()); "
            "import nymph_toolkit.subsystems.cognition as cognition; from nymph_toolkit.contracts.cognition import COGNITION_CONTRACT; "
            "assert Path(cognition.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()); "
            "import nymph_toolkit.subsystems.sleep as sleep; from nymph_toolkit.contracts.sleep import SLEEP_CONTRACT; "
            "assert Path(sleep.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()); "
            "from importlib.metadata import version; import sys; "
            "assert version('nymph-toolkit') == '1.12.0'; "
            "import importlib.util; assert importlib.util.find_spec('vosk') is None; "
            "import nymph_toolkit.adapters.discord_voice as voice; import nymph_toolkit.subsystems.sleep_activity as sleep_activity; "
            "from nymph_toolkit.contracts.voice import VOICE_CONTRACT; from nymph_toolkit.contracts.sleep_activity import SLEEP_ACTIVITY_CONTRACT; "
            "assert Path(voice.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()); "
            "assert Path(sleep_activity.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()); "
            "assert Path(voice.__file__).with_name('bridge.mjs').is_file(); "
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
        subprocess.run([str(python), "-I", str(work / "examples/memory_demo.py")], cwd=work, env=env, check=True)
        subprocess.run([str(python), "-I", str(work / "examples/document_demo.py")], cwd=work, env=env, check=True)
        subprocess.run([str(python), "-I", str(work / "examples/cognition_demo.py")], cwd=work, env=env, check=True)
        subprocess.run([str(python), "-I", str(work / "examples/text_interaction_demo.py")], cwd=work, env=env, check=True)
        subprocess.run([str(python), "-I", str(work / "examples/web_demo.py")], cwd=work, env=env, check=True)
        subprocess.run([str(python), "-I", str(work / "examples/agency_demo.py")], cwd=work, env=env, check=True)
        subprocess.run([str(python), "-I", str(work / "examples/agency_execution_demo.py")], cwd=work, env=env, check=True)
        subprocess.run([str(python), "-I", str(work / "examples/persona_demo.py")], cwd=work, env=env, check=True)
        subprocess.run([str(python), "-I", str(work / "examples/persona_agency_demo.py")], cwd=work, env=env, check=True)
        subprocess.run([str(python), "-I", str(work / "examples/sleep_demo.py")], cwd=work, env=env, check=True)
        subprocess.run([str(python), "-I", str(work / "examples/sleep_activity_demo.py")], cwd=work, env=env, check=True)
        subprocess.run([str(python), "-I", str(work / "examples/voice_audio_demo.py")], cwd=work, env=env, check=True)
        subprocess.run([str(python), "-I", str(work / "examples/input_candidate_demo.py")], cwd=work, env=env, check=True)
        subprocess.run([str(python), "-I", str(work / "examples/runtime_diagnostics_demo.py"), "--seconds", "2"], cwd=work, env=env, check=True)
        subprocess.run([str(python), "-I", str(work / "examples/voice_capture.py"), "--help"], cwd=work, env=env, check=True)
        subprocess.run([str(python), "-I", str(work / "tools/validate_voice_live.py"), "--help"], cwd=work, env=env, check=True)
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
