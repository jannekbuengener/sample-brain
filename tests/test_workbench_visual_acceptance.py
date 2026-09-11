from pathlib import Path
import struct, zlib
import pytest
from src.runtime_provenance import RuntimeManifest, RuntimeReport, RuntimeStatus
from src.workbench_visual_acceptance import *

def report(status=RuntimeStatus.VALID):
    return RuntimeReport(status,"test",RuntimeManifest(1,"main","a"*40,"runtime","python","now"))
def png(path: Path, pixels=b"\x12\x34\x56\xff"):
    def c(k,p): return struct.pack(">I",len(p))+k+p+struct.pack(">I",zlib.crc32(k+p)&0xffffffff)
    path.write_bytes(b"\x89PNG\r\n\x1a\n"+c(b"IHDR",struct.pack(">IIBBBBB",1,1,8,6,0,0,0))+c(b"IDAT",zlib.compress(b"\0"+pixels))+c(b"IEND",b""))
def test_fixture_contract():
    f=build_screen1_visual_fixture_v1(); assert f.version==FIXTURE_VERSION and len(f.browser_rows)==12 and f.browser_rows[2].display_name=="TECH_BASS_01" and len(f.harmony_results)==6 and f.state_ids==REQUIRED_STATE_IDS
@pytest.mark.parametrize("status",[RuntimeStatus.DIRTY,RuntimeStatus.HEAD_MISMATCH,RuntimeStatus.IMPORT_MISMATCH,RuntimeStatus.UNKNOWN])
def test_invalid_runtime_blocks(status):
    with pytest.raises(EvidenceError): validate_runtime_for_visual_acceptance(report(status))
def test_manifest_and_sanity(tmp_path):
    paths={}
    for state in REQUIRED_STATE_IDS: paths[state]=tmp_path/f"{state}.png"; png(paths[state])
    result=build_visual_evidence_manifest(runtime_report=report(),fixture=build_screen1_visual_fixture_v1(),captures=paths,os_name="Windows 11",dpi_scale=100,client_width=CLIENT_WIDTH,client_height=CLIENT_HEIGHT,sanity_results={})
    assert result["states"]==list(REQUIRED_STATE_IDS) and len(result["screenshot_hashes"])==2 and "runtime_root" not in str(result)
    assert validate_capture_sanity(paths[REQUIRED_STATE_IDS[0]],expected_width=1,expected_height=1)["pass"]
