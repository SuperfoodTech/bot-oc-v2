from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))


from backend.vb import _parse_matrix, resolve_brand_owner_name, slugify_owner_name


def test_parse_matrix_reads_owner_from_relational_sheet():
    csv_text = """Owner,Outlet,Portal,Store ID
  A Isyah  ,Ayam Geprek Suroboyo Ampel,WonderFood,21897196
"""

    matrix = _parse_matrix(csv_text)

    assert len(matrix) == 1
    assert matrix[0]["brand"] == "Ayam Geprek Suroboyo Ampel"
    assert matrix[0]["owner"] == "A Isyah"
    assert matrix[0]["stores"] == [
        {
            "store_id": "21897196",
            "source_column": "WonderFood",
            "owner": "A Isyah",
        }
    ]


def test_resolve_brand_owner_name_keeps_existing_specific_owner_over_generic_vb():
    owner_name = resolve_brand_owner_name(
        {
            "owner": "VB",
            "stores": [
                {"owner": "VB"},
            ],
        },
        existing_owner_name="A Isyah",
    )

    assert owner_name == "A Isyah"
    assert slugify_owner_name(owner_name) == "a-isyah"
