"""src.tools.web: allowlist + normalisation offline (recorded DuckDuckGo results), cache, and one live test."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.tools import web  # noqa: E402

# Recorded 2026-10-10 from DDGS().text(..., region="vn-vi", backend="duckduckgo"), plus hand-added off-list hosts.
RECORDED = {
    "query": "thủ tục đăng ký khai sinh site:dichvucong.gov.vn",
    "fetched_at": "2026-10-10T04:30:00+00:00",
    "results": [
        {"title": "Thủ tục đăng ký khai sinh lưu động",
         "href": "https://vpcp.dichvucong.gov.vn/p/home/dvc-tthc-thu-tuc-hanh-chinh-chi-tiet.html?ma_thu_tuc=105200",
         "body": "Cổng Dịch vụ công Quốc gia hỗ trợ thông tin, đăng ký thủ tục hành chính"},
        {"title": "Thủ tục đăng ký khai sinh", "href": "https://moj.gov.vn/portal/thu-tuc-hanh-chinh/chi-tiet-1.001193.html",
         "body": "Bộ Tư pháp"},
        {"title": "Hồ sơ đăng ký khai sinh 2026", "href": "https://thuvienphapluat.vn/hoi-dap-phap-luat/khai-sinh.html",
         "body": "Hồ sơ gồm ..."},
        {"title": "Blog khai sinh", "href": "https://example.com/khai-sinh", "body": "không chính thức"},
        {"title": "Lookalike", "href": "https://gov.vn.evil.com/khai-sinh", "body": "giả mạo"},
        {"title": "Lookalike 2", "href": "https://notdichvucong.gov.vn.co/x", "body": "giả mạo"},
        {"title": "Duplicate", "href": "https://moj.gov.vn/portal/thu-tuc-hanh-chinh/chi-tiet-1.001193.html", "body": "dup"},
        {"title": "FTP", "href": "ftp://dichvucong.gov.vn/x", "body": "not http"},
    ],
}


@pytest.mark.parametrize("url,tier", [
    ("https://dichvucong.gov.vn/p/home/x.html", "web_official"),
    ("https://vpcp.dichvucong.gov.vn/p/home/x.html", "web_official"),
    ("https://moj.gov.vn/portal/x", "web_official"),
    ("http://DAKLAK.GOV.VN/x", "web_official"),
    ("https://thuvienphapluat.vn/van-ban/x", "web_other"),
    ("https://www.luatvietnam.vn/x", "web_other"),
    ("https://gov.vn.evil.com/x", None),
    ("https://evilgov.vn/x", None),
    ("https://xaydungchinhsach.chinhphu.vn/x", "web_official"),
    ("https://baochinhphu.vn/x", "web_official"),
    ("https://notchinhphu.vn/x", None),
    ("https://notthuvienphapluat.vn/x", None),
    ("https://example.com", None),
    ("javascript:alert(1)", None),
    ("", None),
])
def test_classify_url(url, tier):
    assert web.classify_url(url) == tier


def test_allowlist_file_matches_default():
    assert web.load_allowlist() == web.DEFAULT_ALLOWLIST


def test_to_evidence_filters_and_normalises():
    evs = web.to_evidence(RECORDED, procedure_id="1.001193")
    assert [e["structured"]["domain"] for e in evs] == ["vpcp.dichvucong.gov.vn", "moj.gov.vn", "thuvienphapluat.vn"]
    assert [e["tier"] for e in evs] == ["web_official", "web_official", "web_other"]
    e = evs[0]
    assert e["evidence_id"] == web.web_id(e["source_url"]) and e["evidence_id"].startswith("web:")
    assert e["retrieved_at"] == RECORDED["fetched_at"] and e["procedure_id"] == "1.001193"
    assert e["section"] is None and e["text"].startswith("Thủ tục đăng ký khai sinh lưu động")


def test_web_search_uses_cache_and_site(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_WEB_CACHE", str(tmp_path))
    calls = []

    def fake_live(q, n, backend, retries=1):
        calls.append(q)
        return RECORDED["results"]

    monkeypatch.setattr(web, "_search_live", fake_live)
    a = web.web_search("đăng ký khai sinh", site="dichvucong.gov.vn", official_only=True)
    b = web.web_search("đăng ký khai sinh", site="dichvucong.gov.vn", official_only=True)
    assert calls == ["đăng ký khai sinh site:dichvucong.gov.vn"]  # second call served from cache
    assert a == b and {e["tier"] for e in a} == {"web_official"}
    idx = [json.loads(x) for x in (tmp_path / "index.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(idx) == 1 and idx[0]["n"] == len(RECORDED["results"]) and len(idx[0]["sha256"]) == 64
    assert idx[0]["backend"] == "searxng"  # first backend in the default chain
    assert all(web._host_in(e["source_url"], "dichvucong.gov.vn") for e in a)  # site enforced post hoc
    assert [e["structured"]["domain"] for e in a] == ["vpcp.dichvucong.gov.vn"]


def test_backend_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_WEB_CACHE", str(tmp_path))
    monkeypatch.setenv("APP_WEB_BACKEND", "duckduckgo,bing")
    tried = []

    def fake_live(q, n, backend, retries=1):
        tried.append(backend)
        return [] if backend == "duckduckgo" else RECORDED["results"]

    monkeypatch.setattr(web, "_search_live", fake_live)
    r = web.raw_search("q")
    assert tried == ["duckduckgo", "bing"] and r["backend"] == "bing" and r["results"]


def test_search_error_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_WEB_CACHE", str(tmp_path))
    monkeypatch.setenv("APP_WEB_BACKEND", "duckduckgo")

    class Boom:
        def __init__(self, **kw): ...
        def text(self, *a, **kw): raise RuntimeError("202 Ratelimit")

    import ddgs
    monkeypatch.setattr(ddgs, "DDGS", Boom)
    with pytest.raises(web.WebSearchError):  # every backend errored
        web.web_search("x")
    assert not list(tmp_path.glob("*.json"))  # failures are not cached


def test_empty_answer_not_cached(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_WEB_CACHE", str(tmp_path))
    monkeypatch.setattr(web, "_search_live", lambda q, n, b, retries=1: [])
    assert web.web_search("x") == []
    assert not list(tmp_path.glob("*.json"))


@pytest.mark.network
def test_live_search(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_WEB_CACHE", str(tmp_path))
    raw = web.raw_search("thủ tục đăng ký khai sinh site:dichvucong.gov.vn", max_results=5)
    if not raw["results"]:
        pytest.skip(f"every backend in {web.backends()} returned nothing (search engines throttling this host)")
    evs = web.web_search("thủ tục đăng ký khai sinh", site="dichvucong.gov.vn", max_results=5)  # served from cache
    assert evs, f"results came back but none allowlisted: {[r.get('href') for r in raw['results']]}"
    assert all(e["tier"] == "web_official" for e in evs)

# Recorded 2026-10-10 from the local SearxNG (infra/searxng), GET /search?format=json&language=vi-VN, first 8 results.
SEARXNG_RECORDED = {
 "query": "thủ tục cấp lại thẻ căn cước",
 "results": [
  {
   "url": "https://dichvucong.bocongan.gov.vn/bocongan/bothutuc/tthc?matt=26097",
   "title": "Cấp lại thẻ căn cước (thực hiện tại cấp huyện)",
   "content": "+ Công dân đến cơ quan quản lý căn cước của Công an cấp tỉnh đề nghị cấp lại thẻ căn cước hoặc thông qua Cổng dịch vụ công quốc gia, Cổng dịch vụ công Bộ Công an, ứng dụng định danh quốc gia lựa chọn thủ tục cấp lại thẻ căn cước, kiểm tra thông tin của ...",
   "engines": [
    "duckduckgo"
   ]
  },
  {
   "url": "https://luatvietnam.vn/hanh-chinh/huong-dan-lam-thu-tuc-cap-cap-doi-cap-lai-the-can-cuoc-qua-vneid-tu-15-3-2026-570-107698-article.html",
   "title": "Hướng dẫn làm thủ tục cấp, cấp đổi, cấp lại thẻ căn cước qua VNeID từ ...",
   "content": "Từ ngày 15/3/2026, thủ tục cấp, cấp đổi, cấp lại thẻ Căn cước có thể được thực hiện trực tuyến thông qua Cổng dịch vụ công quốc gia hoặc ứng dụng định danh điện tử quốc gia VNeID theo quy định tại Nghị định 58/2026/NĐ-CP.",
   "engines": [
    "duckduckgo"
   ]
  },
  {
   "url": "https://dichvucong.bocongan.gov.vn/bocongan/bothutuc?linh_vuc=CAP_CCCD",
   "title": "Cổng Dịch Vụ Công Trực Tuyến",
   "content": "Cấp thẻ căn cước cho người dưới 14 tuổi (thực hiện tại cấp trung ương) Cấp thẻ căn cước cho người dưới 14 tuổi (thực hiện tại cấp tỉnh) Cấp xác nhận số chứng minh nhân dân 09 số, số định danh cá nhân (thực hiện tại cấp trung ương)",
   "engines": [
    "duckduckgo"
   ]
  },
  {
   "url": "https://luatmaison.vn/thu-tuc-cap-lai-can-cuoc-cong-dan-bi-mat/",
   "title": "Hướng dẫn thủ tục cấp lại căn cước công dân bị mất 2026",
   "content": "Hướng dẫn chi tiết thủ tục cấp lại căn cước công dân bị mất mới nhất 2026: Hồ sơ, lệ phí, cách làm online và lưu ý cập nhật thuế sau khi nhận thẻ.",
   "engines": [
    "duckduckgo"
   ]
  },
  {
   "url": "https://thuvienphapluat.vn/chinh-sach-phap-luat-moi/vn/thu-tuc-hanh-chinh-online/98956/huong-dan-cap-doi-the-can-cuoc-online-chi-tiet-nhat-2025",
   "title": "Hướng dẫn cấp đổi thẻ căn cước online chi tiết nhất 2025",
   "content": "Bài viết dưới đây sẽ hướng dẫn chi tiết cách cấp đổi thẻ căn cước online chi tiết nhất 2025.",
   "engines": [
    "duckduckgo"
   ]
  },
  {
   "url": "https://xaydungchinhsach.chinhphu.vn/quy-dinh-moi-trinh-tu-thu-tuc-cap-doi-cap-lai-the-can-cuoc-119240627144340876.htm",
   "title": "Quy định mới: Trình tự, thủ tục cấp, đổi, cấp lại thẻ căn cước",
   "content": "Trình tự, thủ tục cấp, cấp đổi, cấp lại thẻ căn cước từ ngày 1/7/2024 sẽ được thực hiện theo Nghị định số 70/2024/NĐ-CP của Chính phủ.",
   "engines": [
    "duckduckgo"
   ]
  },
  {
   "url": "https://thuvienphapluat.vn/chinh-sach-phap-luat-moi/vn/ho-tro-phap-luat/chinh-sach-moi/66103/thu-tuc-cap-cap-doi-cap-lai-the-can-cuoc-theo-hinh-thuc-truc-tuyen-tu-ngay-01-7-2024",
   "title": "Thủ tục cấp, cấp đổi, cấp lại thẻ căn cước theo hình thức trực tuyến từ ...",
   "content": "Công dân đến cơ quan quản lý căn cước theo thời gian, địa điểm đã đăng ký để thực hiện thủ tục cấp, cấp đổi, cấp lại thẻ căn cước theo trình tự, thủ tục quy định tại khoản 1 Điều 21 Nghị định 70/2024/NĐ-CP.",
   "engines": [
    "duckduckgo"
   ]
  },
  {
   "url": "https://baochinhphu.vn/trinh-tu-thu-tuc-cap-doi-cap-lai-the-can-cuoc-moi-tu-ngay-1-7-102240627092012686.htm",
   "title": "Trình tự, thủ tục cấp, đổi, cấp lại thẻ căn cước mới từ ngày 1/7",
   "content": "Nghị định số 70/2024/NĐ-CP quy định trình tự, thủ tục cấp, cấp đổi, cấp lại thẻ căn cước tại cơ quan quản lý căn cước và thông qua Cổng dịch vụ công quốc gia, Cổng dịch vụ công Bộ Công an, ứng dụng định danh quốc gia.",
   "engines": [
    "duckduckgo"
   ]
  }
 ],
 "unresponsive_engines": [
  [
   "brave",
   "Suspended: too many requests"
  ],
  [
   "google",
   "Suspended: access denied"
  ]
 ]
}


class _Resp:
    def __init__(self, data, status=200):
        self._data, self.status_code = data, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise web.httpx.HTTPStatusError("err", request=None, response=None)

    def json(self):
        return self._data


def test_searxng_recorded_response(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_WEB_CACHE", str(tmp_path))
    monkeypatch.setenv("APP_WEB_BACKEND", "searxng")
    monkeypatch.setattr(web, "MIN_INTERVAL_S", 0)
    seen = {}

    def fake_get(url, params=None, timeout=None):
        seen.update(url=url, params=params)
        return _Resp(SEARXNG_RECORDED)

    monkeypatch.setattr(web.httpx, "get", fake_get)
    evs = web.web_search("thủ tục cấp lại thẻ căn cước")
    assert seen["url"].endswith("/search") and seen["params"]["format"] == "json" and seen["params"]["safesearch"] == 0
    # gov.vn, chinhphu.vn, baochinhphu.vn → official; luatvietnam/thuvienphapluat → other; luatmaison.vn → dropped
    assert [e["tier"] for e in evs] == ["web_official", "web_other", "web_official", "web_other", "web_official",
                                        "web_other", "web_official"]
    assert evs[0]["source_url"] == "https://dichvucong.bocongan.gov.vn/bocongan/bothutuc/tthc?matt=26097"
    idx = json.loads((tmp_path / "index.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert idx["backend"] == "searxng"
    assert web.web_search("thủ tục cấp lại thẻ căn cước", max_results=2, official_only=True)[1]["tier"] == "web_official"


def test_searxng_down_falls_back(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_WEB_CACHE", str(tmp_path))
    monkeypatch.setenv("APP_WEB_BACKEND", "searxng,duckduckgo")
    monkeypatch.setenv("SEARXNG_URL", "http://127.0.0.1:9")  # nothing listens on the discard port
    monkeypatch.setattr(web, "MIN_INTERVAL_S", 0)

    class FakeDDGS:
        def __init__(self, **kw): ...
        def text(self, *a, **kw): return RECORDED["results"]

    import ddgs
    monkeypatch.setattr(ddgs, "DDGS", FakeDDGS)
    r = web.raw_search("q")
    assert r["backend"] == "duckduckgo" and r["results"]


def _searxng_up() -> bool:
    try:
        return web.httpx.get(web.searxng_url() + "/healthz", timeout=2).status_code == 200
    except web.httpx.HTTPError:
        return False


@pytest.mark.network
@pytest.mark.skipif(not _searxng_up(), reason="local SearxNG not running (infra/searxng/up.sh)")
def test_live_searxng(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_WEB_CACHE", str(tmp_path))
    monkeypatch.setenv("APP_WEB_BACKEND", "searxng")
    raw = web.raw_search("thủ tục đăng ký khai sinh")
    assert raw["backend"] == "searxng" and raw["results"], "SearxNG returned nothing"
    assert web.web_search("thủ tục đăng ký khai sinh"), f"no allowlisted host in {[r['href'] for r in raw['results']]}"
