# VERIFICATION — bca-portal records vs raw pages

Date: 2026-10-10. Records were picked with `random.seed(5013); random.sample(<18 procedure_ids>, 3)` → 1.010028, 2.001194, 2.000200.
Method: an independent regex extraction from the raw HTML (`data/raw/dvc/bca-portal/<matt>.html`, not BeautifulSoup, so the parser's own code is not reused),
compared with the parsed JSON field by field. Items were compared verbatim after whitespace collapse.

| record | field | match | note |
|---|---|---|---|
| 1.010028 Xóa đăng ký tạm trú (matt 26552) | required_documents | yes | 2 raw rows = 2 parsed, same order, identical text |
| 1.010028 | quantity | yes | raw "Bản chính: 1 Bản sao: 0" ×2 → quantity_text "Bản chính: 1; Bản sao: 0", quantity 1 |
| 1.010028 | fees | yes (with gap) | raw Phí = "a" (placeholder, left unknown); Lệ Phí = "Không" → `miễn lệ phí` |
| 1.010028 | receiving_agency | yes | "Công an Xã" |
| 1.010028 | processing_time | yes | raw "Trực tiếp 02 Ngày làm việc … Trực tuyến 02 Ngày làm việc" → "Trực tiếp: 02 Ngày làm việc; Trực tuyến: 02 Ngày làm việc" |
| 2.001194 Cấp lại thẻ căn cước – cấp tỉnh (matt 26093) | required_documents | yes | 3 = 3, same order; the two case headings (h4) are carried in `note` |
| 2.001194 | quantity | yes | 1/0 ×3 |
| 2.001194 | fees | yes (unknown) | raw Phí = "Trực tiếp Trực tuyến" (channel labels only); Lệ Phí = "07 Ngày làm việc Chưa quy định." ×2 → fees `[]`. The page states no amount, so nothing was recorded |
| 2.001194 | receiving_agency | yes | "Phòng cảnh sát quản lý hành chính về trật tự xã hội" |
| 2.001194 | processing_time | yes | 07 Ngày làm việc for both channels |
| 2.000200 Cấp thẻ căn cước ≥14 tuổi – cấp tỉnh (matt 26052) | required_documents | yes | 4 = 4, same order |
| 2.000200 | quantity | yes | 1/0 ×4 |
| 2.000200 | fees | yes | Phí "Không" → `miễn phí`; Lệ Phí "Không" → `miễn lệ phí` |
| 2.000200 | receiving_agency | yes | "Phòng cảnh sát quản lý hành chính về trật tự xã hội" |
| 2.000200 | processing_time | yes | raw "07 ngày làm việc" (no channel labels) → kept verbatim |

Result: 15/15 field checks match the raw page. Fee "unknown" cases are faithful to the page, which shows placeholders or "Chưa quy định."; they are not parser misses.
Caveat: "matches the page" ≠ "correct in law". For example, the portal shows no amount for cấp đổi/cấp lại căn cước, which normally carry a lệ phí. See STATUS → Findings.
