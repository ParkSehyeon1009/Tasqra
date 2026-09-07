from app.services.document_package import infer_package


def test_related_procurement_files_share_package_key():
    names = [
        "[공고서](재공고)주민참여예산제도 개선 및 내실화 방안 연구용역.hwpx",
        "[과업지시서]주민참여예산제도 개선 및 내실화 방안 연구용역.hwpx",
        "[제안요청서]주민참여예산제도 개선 및 내실화 방안 연구용역.hwpx",
    ]
    inferred = [infer_package(name) for name in names]
    assert len({key for key, _ in inferred}) == 1
    assert [role for _, role in inferred] == ["NOTICE", "STATEMENT_OF_WORK", "RFP"]


def test_generic_filename_is_not_automatically_grouped():
    assert infer_package("공고문.pdf") == (None, "NOTICE")
