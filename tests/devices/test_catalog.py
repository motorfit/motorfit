import json
import tomllib
from pathlib import Path

import can
import pytest

from motor_identification.cli import main
from motor_identification.devices.registry import driver
from motor_identification.devices.spec import MotorSpec

ROOT = Path(__file__).resolve().parents[2]


def test_catalog_matches_native_profiles_without_hardware(capsys, monkeypatch):
    def no_can(*args, **kwargs):
        raise AssertionError("Listing models must not open CAN")

    monkeypatch.setattr(can, "Bus", no_can)
    main(["motors", "--json"])
    catalog = json.loads(capsys.readouterr().out)
    profiles = ROOT / "configs/motors"
    assert set(catalog["families"]) == {p.name for p in profiles.iterdir() if p.is_dir()}
    for family, info in catalog["families"].items():
        files = list((profiles / family).glob("*.toml"))
        assert set(info["models"]) == {p.stem for p in files}
        assert info["bam_record_fit"] and driver(family)
        for path in files:
            assert MotorSpec.from_dict(tomllib.loads(path.read_text())).family == family
    assert catalog["families"]["robstride"]["hardware_validated_models"] == ["rs05"]
    assert not catalog["families"]["damiao"]["hardware_validated_models"]
    assert not catalog["unsupported_families"]


def test_unknown_command_is_rejected(capsys):
    with pytest.raises(SystemExit) as result:
        main(["unknown-command", "--help"])
    assert result.value.code == 2
    assert "invalid choice: 'unknown-command'" in capsys.readouterr().err


@pytest.mark.parametrize("family", ["invalid"])
def test_non_mit_families_cannot_silently_use_mit_bam_model(family):
    with pytest.raises(ValueError, match="Unsupported motor family"):
        MotorSpec.from_dict({"family": family})
    with pytest.raises(ValueError, match="No BAM acquisition adapter"):
        driver(family)
