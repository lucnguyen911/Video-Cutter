from pathlib import Path

from build_protected import remove_accidental_windows_icu, synchronize_msvc_runtime


def test_synchronize_msvc_runtime_replaces_older_python_copy(tmp_path: Path):
    internal = tmp_path / "Video_Cutter" / "_internal"
    qt_bin = internal / "PyQt6" / "Qt6" / "bin"
    qt_bin.mkdir(parents=True)
    (internal / "VCRUNTIME140.dll").write_bytes(b"old-python-runtime")
    (qt_bin / "vcruntime140.dll").write_bytes(b"new-qt-runtime")
    (qt_bin / "msvcp140.dll").write_bytes(b"matching-msvcp")

    copied = synchronize_msvc_runtime(tmp_path / "Video_Cutter")

    assert "vcruntime140.dll" in copied
    assert "msvcp140.dll" in copied
    assert (internal / "VCRUNTIME140.dll").read_bytes() == b"new-qt-runtime"
    assert (internal / "msvcp140.dll").read_bytes() == b"matching-msvcp"


def test_remove_accidental_windows_icu_uses_system_runtime(tmp_path: Path):
    dist = tmp_path / "Video_Cutter"
    internal = dist / "_internal"
    qt_bin = internal / "PyQt6" / "Qt6" / "bin"
    system_dir = tmp_path / "Windows" / "System32"
    qt_bin.mkdir(parents=True)
    system_dir.mkdir(parents=True)
    (system_dir / "icuuc.dll").write_bytes(b"windows-icu")
    (internal / "icuuc.dll").write_bytes(b"foreign-poppler-icu")
    (internal / "icudt78.dll").write_bytes(b"foreign-poppler-data")

    removed = remove_accidental_windows_icu(dist, system_dir=system_dir)

    assert removed == ["icudt78.dll", "icuuc.dll"]
    assert not (internal / "icuuc.dll").exists()
    assert not (internal / "icudt78.dll").exists()
    assert (system_dir / "icuuc.dll").read_bytes() == b"windows-icu"
