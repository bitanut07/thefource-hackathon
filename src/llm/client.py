import re
import unicodedata
from collections.abc import Callable
from typing import Protocol

from config import Settings
from llm.schemas import StructuredQuery


class LLMClient(Protocol):
    async def extract_structured_query(self, text: str) -> StructuredQuery:
        """Convert untrusted user text into the application's structured query."""
        ...


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.casefold().replace("đ", "d"))
    without_accents = "".join(
        character for character in decomposed if unicodedata.category(character) != "Mn"
    )
    return re.sub(r"[^a-z0-9]+", " ", without_accents).strip()


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    padded_text = f" {text} "
    return any(f" {phrase} " in padded_text for phrase in phrases)


def _extract_location(text: str) -> str | None:
    district_match = re.search(r"\bquan\s*(\d{1,2})\b", text)
    if district_match is not None:
        return f"Quận {district_match.group(1)}"

    locations = (
        (("tp hcm", "tphcm", "ho chi minh", "sai gon"), "TP.HCM"),
        (("ha noi",), "Hà Nội"),
        (("da nang",), "Đà Nẵng"),
        (("hai phong",), "Hải Phòng"),
        (("can tho",), "Cần Thơ"),
        (("online", "truc tuyen"), "online"),
    )
    for aliases, canonical_name in locations:
        if _contains_any(text, aliases):
            return canonical_name
    return None


def _extract_time(text: str) -> str | None:
    times = (
        (("cuoi tuan",), "cuối tuần"),
        (("hom nay",), "hôm nay"),
        (("ngay mai",), "ngày mai"),
        (("buoi sang",), "buổi sáng"),
        (("buoi chieu",), "buổi chiều"),
        (("buoi toi",), "buổi tối"),
    )
    for aliases, canonical_name in times:
        if _contains_any(text, aliases):
            return canonical_name
    return None


def _extract_target_user(text: str) -> str | None:
    grade_words = {
        "mot": 1,
        "hai": 2,
        "ba": 3,
        "bon": 4,
        "tu": 4,
        "nam": 5,
        "sau": 6,
        "bay": 7,
        "tam": 8,
        "chin": 9,
        "muoi": 10,
        "muoi mot": 11,
        "muoi hai": 12,
    }
    grade_match = re.search(r"\blop\s*(\d{1,2})\b", text)
    if grade_match is not None:
        grade = int(grade_match.group(1))
        if 1 <= grade <= 12:
            return f"grade_{grade}_student"

    grade_items = sorted(grade_words.items(), key=lambda item: len(item[0]), reverse=True)
    for word, grade in grade_items:
        if re.search(rf"\blop\s+{word}\b", text):
            return f"grade_{grade}_student"

    if _contains_any(text, ("cho chau", "tre em", "hoc sinh")):
        return "child_student"
    if _contains_any(text, ("sinh vien",)):
        return "student"
    if _contains_any(text, ("nguoi cao tuoi", "nguoi gia")):
        return "senior"
    return None


def _extract_healthcare(text: str) -> StructuredQuery | None:
    healthcare_terms = (
        "kham",
        "bac si",
        "benh vien",
        "phong kham",
        "y te",
        "nha khoa",
        "tiem chung",
    )
    if not _contains_any(text, healthcare_terms):
        return None

    services = (
        (("kham mat", "bac si mat"), "khám mắt"),
        (("nha khoa", "kham rang", "rang"), "nha khoa"),
        (("tai mui hong",), "khám tai mũi họng"),
        (("da lieu",), "khám da liễu"),
        (("tiem chung",), "tiêm chủng"),
        (("kham", "bac si", "benh vien", "phong kham", "y te"), "khám bệnh"),
    )
    service = next(
        canonical_name for aliases, canonical_name in services if _contains_any(text, aliases)
    )
    return StructuredQuery(
        intent="find_medical_service",
        category="healthcare",
        service=service,
        location=_extract_location(text),
        time=_extract_time(text),
        target_user=_extract_target_user(text),
    )


def _extract_utilities(text: str) -> StructuredQuery | None:
    utility_terms = (
        "tien dien",
        "tien nuoc",
        "hoa don dien",
        "hoa don nuoc",
        "hoa don tien ich",
        "dien luc",
        "dong tien dien",
        "thanh toan tien dien",
        "thanh toan hoa don",
    )
    if not _contains_any(text, utility_terms):
        return None

    if _contains_any(text, ("tien nuoc", "hoa don nuoc")):
        service = "thanh toán tiền nước"
    elif _contains_any(text, ("tra cuu", "xem hoa don")):
        service = "tra cứu hóa đơn tiện ích"
    else:
        service = "thanh toán tiền điện"

    return StructuredQuery(
        intent="pay_utility_bill",
        category="utilities",
        service=service,
        location=_extract_location(text),
        time=_extract_time(text),
        target_user=_extract_target_user(text),
    )


def _extract_education(text: str) -> StructuredQuery | None:
    education_terms = (
        "hoc",
        "giao duc",
        "khoa hoc",
        "gia su",
        "on thi",
    )
    if not _contains_any(text, education_terms):
        return None

    subject_terms = (
        (("toan",), "học toán"),
        (("tieng anh", "anh van"), "học tiếng Anh"),
        (("ngu van", "van hoc"), "học ngữ văn"),
        (("vat ly",), "học vật lý"),
        (("hoa hoc",), "học hóa học"),
        (("lap trinh",), "học lập trình"),
        (("gia su",), "gia sư"),
        (("on thi",), "ôn thi"),
    )
    service = next(
        (
            canonical_name
            for aliases, canonical_name in subject_terms
            if _contains_any(text, aliases)
        ),
        None,
    )
    needs_clarification = service is None
    return StructuredQuery(
        intent="find_education_service",
        category="education",
        service=service,
        location=_extract_location(text),
        time=_extract_time(text),
        target_user=_extract_target_user(text),
        needs_clarification=needs_clarification,
        clarification_field="service" if needs_clarification else None,
    )


def _extract_transport(text: str) -> StructuredQuery | None:
    transport_terms = (
        "tuyen xe",
        "xe buyt",
        "tram xe",
        "giao thong cong cong",
        "tra cuu xe",
        "duong di bang xe",
        "bus",
    )
    if not _contains_any(text, transport_terms):
        return None

    if _contains_any(text, ("xe buyt", "bus")):
        service = "tra cứu tuyến xe buýt"
    else:
        service = "tra cứu tuyến xe"
    return StructuredQuery(
        intent="find_public_transport",
        category="transport_public",
        service=service,
        location=_extract_location(text),
        time=_extract_time(text),
        target_user=_extract_target_user(text),
    )


_CATEGORY_EXTRACTORS: tuple[Callable[[str], StructuredQuery | None], ...] = (
    _extract_transport,
    _extract_utilities,
    _extract_education,
    _extract_healthcare,
)


def _is_explicit_action_out_of_scope(text: str) -> bool:
    action_phrases = (
        "ve may bay",
        "dat ve may bay",
        "mua ve may bay",
        "dat phong",
        "dat lich giup",
        "dat lich ho",
        "thanh toan giup",
        "thanh toan ho",
        "chuyen tien",
        "mua ho",
        "goi mon",
    )
    return _contains_any(text, action_phrases)


class RuleBasedIntentExtractor:
    """Deterministic Vietnamese extractor for local development and CI."""

    async def extract_structured_query(self, text: str) -> StructuredQuery:
        normalized_text = _normalize(text)
        if not normalized_text:
            return StructuredQuery(
                intent="unknown",
                needs_clarification=True,
                clarification_field="service",
            )

        if _is_explicit_action_out_of_scope(normalized_text):
            return StructuredQuery(intent="unknown", out_of_scope=True)

        for extractor in _CATEGORY_EXTRACTORS:
            query = extractor(normalized_text)
            if query is not None:
                return query

        return StructuredQuery(intent="unknown", out_of_scope=True)


class ConfiguredLLMClient:
    settings: Settings
    _client: LLMClient

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        provider = settings.llm_provider.strip().casefold()
        if provider != "fake":
            raise ValueError(
                f"LLM provider {settings.llm_provider!r} chưa được tích hợp; "
                "hãy dùng LLM_PROVIDER=fake cho chế độ local."
            )
        self._client = RuleBasedIntentExtractor()

    async def extract_structured_query(self, text: str) -> StructuredQuery:
        return await self._client.extract_structured_query(text)
