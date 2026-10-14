# Data verification sheet

Generated 2026-10-10 by `scripts/make_verification_sheet.py --n 10 --seed 42` from 57 procedures (data/processed/moj, data/processed/bca-portal, data/processed/daklak; prefer moj > bca-portal > daklak).
Open each source URL, compare field by field, tick ☐ → ☑ when the record matches the source verbatim,
otherwise write the correct value in the last column.

| # | procedure_id | title | source |
|---|---|---|---|
| 1 | 1.000094 | Thủ tục đăng ký kết hôn có yếu tố nước ngoài tại khu vực biên giới | moj |
| 2 | 1.000689 | Thủ tục đăng ký khai sinh kết hợp đăng ký nhận cha, mẹ, con | moj |
| 3 | 1.000757 | Cấp lại thẻ căn cước (thực hiện tại cấp trung ương) | bca-portal |
| 4 | 1.000889 | Cấp đổi thẻ căn cước (thực hiện tại cấp trung ương) | bca-portal |
| 5 | 1.001669 | Thủ tục đăng ký giám hộ có yếu tố nước ngoài | moj |
| 6 | 1.001695 | Thủ tục đăng ký khai sinh kết hợp đăng ký nhận cha, mẹ, con có yếu tố nước ngoài | moj |
| 7 | 1.002755 | Gia hạn tạm trú | bca-portal |
| 8 | 2.000513 | Thủ tục đăng ký lại kết hôn có yếu tố nước ngoài | moj |
| 9 | 2.000756 | Thủ tục đăng ký chấm dứt giám hộ có yếu tố nước ngoài | moj |
| 10 | 2.002189 | Thủ tục ghi vào Sổ hộ tịch việc kết hôn của công dân Việt Nam đã được giải quyết tại cơ quan có thẩm quyền của nước ngoài | moj |

## 1. 1.000094 — Thủ tục đăng ký kết hôn có yếu tố nước ngoài tại khu vực biên giới

- Source: [Thủ tục đăng ký kết hôn có yếu tố nước ngoài tại khu vực biên giới](https://moj.gov.vn/portal/thu-tuc-hanh-chinh/chi-tiet-1.000094.html) · `moj-portal#1.000094` · locator moj.gov.vn TTHC chi tiết mã 1.000094; cơ quan theo 1833/QĐ-BTP Phần I, mục A.34 (https://cdn.haiphong.gov.vn/gov-hpg/6855/tintuc/2025/11/1833638988795114181791.pdf) · retrieved 2026-10-10 · effective _null_
- Record file: `data/processed/moj/1.000094.json`

| ✓ | Field | Value in record | Correction / note |
|---|---|---|---|
| ☐ | title | Thủ tục đăng ký kết hôn có yếu tố nước ngoài tại khu vực biên giới | |
| ☐ | variant_of | 1.000894 | |
| ☐ | field | Hộ tịch | |
| ☐ | level | cấp xã | |
| ☐ | jurisdiction | toàn quốc | |
| ☐ | receiving_agency | UBND cấp xã | |
| ☐ | channels | Trực tuyến; Trực tiếp; Qua bưu chính công ích | |
| ☐ | required_documents[1] | Mẫu hộ tịch điện tử tương tác đăng ký kết hôn (do người yêu cầu cung cấp thông tin theo hướng dẫn trên Cổng dịch vụ công, nếu người có yêu cầu lựa chọn nộp hồ sơ theo hình thức trực tuyến) · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents[2] | Giấy tờ do cơ quan có thẩm quyền của nước láng giềng cấp không quá 06 tháng tính đến ngày nhận hồ sơ, xác nhận công dân nước láng giềng hiện tại là người không có vợ hoặc không có chồng; · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents[3] | Trường hợp người yêu cầu đăng k ý hộ tịch lựa chọn nhận kết quả tại Trung tâm Phục vụ hành chính công thì người yêu cầu đăng ký hộ tịch phải xuất trình giấy tờ tuỳ thân, nộp các giấy tờ là thành phần hồ sơ theo quy định; Trường hợp người yêu cầu đăng ký hộ tịch không lựa chọn nhận kết quả tại Trung tâm Phục vụ hành chính công thì người yêu cầu đăng ký hộ tịch nộp các giấy tờ là thành phần hồ sơ theo quy định trước khi nhận kết quả. · SL 2 (Số bản chính: 1; Số bản sao: 1) · bắt buộc _null_ | |
| ☐ | required_documents[4] | Bản sao giấy tờ chứng minh nhân thân, giấy tờ chứng minh nơi thường trú ở khu vực biên giới của công dân nước láng giềng. · SL 1 (Số bản chính: 0; Số bản sao: 1) · bắt buộc _null_ | |
| ☐ | required_documents[5] | Giấy tờ do cơ quan có thẩm quyền của nước ngoài cấp, công chứng hoặc xác nhận để sử dụng cho việc đăng ký hộ tịch tại Việt Nam phải được hợp pháp hóa lãnh sự theo quy định của pháp luật, trừ trường hợp được miễn theo điều ước quốc tế mà Việt Nam là thành viên. · SL 2 (Số bản chính: 1; Số bản sao: 1) · bắt buộc _null_ | |
| ☐ | required_documents[6] | Hộ chiếu/Thẻ căn cước công dân/Thẻ căn cước/Căn cước điện tử/Giấy chứng nhận căn cước hoặc các giấy tờ khác có dán ảnh và thông tin cá nhân do cơ quan có thẩm quyền cấp, còn giá trị sử dụng (sau đây gọi tắt là giấy tờ tùy thân) để chứng minh về nhân thân khi làm thủ tục trực tiếp tại cơ quan đăng ký hộ tịch. · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents[7] | Tờ khai đăng ký kết hôn theo mẫu, có đủ thông tin của hai bên nam, nữ. Hai bên nam, nữ có thể khai chung vào một Tờ khai đăng ký kết hôn (nếu người có yêu cầu lựa chọn nộp hồ sơ theo hình thức trực tiếp); · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents[8] | Trường hợp người yêu cầu đăng ký hộ tịch không cung cấp được giấy tờ theo quy định hoặc giấy tờ nộp, xuất trình bị tẩy xóa, sửa chữa, làm giả thì cơ quan đăng ký hộ tịch có thẩm quyền hủy bỏ kết quả đăng ký hộ tịch. · SL 2 (Số bản chính: 1; Số bản sao: 1) · bắt buộc _null_ | |
| ☐ | required_documents[9] | Giấy tờ chứng minh nơi cư trú của công dân Việt Nam để chứng minh thẩm quyền đăng ký kết hôn trong trường hợp cơ quan đăng ký hộ tịch không thể khai thác được thông tin về nơi cư trú của công dân theo các phương thức quy định tại khoản 2 Điều 14 Nghị định số 104/2022/NĐ-CP ngày 21/12/2022 của Chính phủ. Trường hợp các thông tin về giấy tờ chứng minh nơi cư trú đã được khai thác từ Cơ sở dữ liệu quốc gia về dân cư bằng các phương thức này thì người có yêu cầu không phải xuất trình (theo hình thức trực tiếp) hoặc tải lên (theo hình thức trực tuyến). · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents — none missing vs source | 9 items | |
| ☐ | fees[1] | theo HĐND tỉnh · Mức lệ phí cụ thể do Hội đồng nhân dân tỉnh, thành phố trực thuộc Trung ương quyết định · theo tỉnh | |
| ☐ | fees[2] | miễn lệ phí · người thuộc gia đình có công với cách mạng; người thuộc hộ nghèo; người khuyết tật · toàn quốc | |
| ☐ | processing_time | 03 ngày làm việc. Trường hợp cần xác minh thì thời hạn giải quyết không quá 08 ngày làm việc | |
| ☐ | steps (count) | 6 | |
| ☐ | legal_basis | 66.7/2025/NQ-CP; 85/2019/TT-BTC – Thông tư 85/2019/TT-BTC; 04/2020/TT-BTP – Thông tư 04/2020/TT-BTP; 08/2025/TT-BTP – Thông tư số 08/2025/TT-BTP ngày 12/6/2025 của Bộ trưởng Bộ Tư pháp quy định về phân định thẩm quyền của chính quyền địa phương 02 cấp và phân cấp trong lĩnh vực quản lý nhà nước của Bộ Tư pháp; 18/2026/NĐ-CP – Sửa đổi, bổ sung một số nghị định để cắt giảm, đơn giản hóa thủ tục hành chính, điều kiện kinh doanh thuộc phạm vi quản lý của Bộ Tư pháp; Thông tư số 03/2023/TT-BTP – Thông tư số 03/2023/TT-BTP ngày 02/8/2023 của Bộ trưởng Bộ Tư pháp; 104/2022/NĐ-CP – Nghị định sửa đổi, bổ sung một số điều của các nghị định liên quan đến việc nộp, xuất trình sổ hộ khẩu, sổ tạm trú giấy khi thực hiện thủ tục hành chính, cung cấp dịch vụ công; 120/2025/NĐ-CP – Nghị định số 120/2025/NĐ-CP ngày 11/6/2025 của Chính phủ quy định về phân định thẩm quyền của chính quyền địa phương 02 cấp trong lĩnh vực quản lý nhà nước của Bộ Tư pháp.; 01/2022/TT-BTP – Thông tư sửa đổi; 87/2020/NĐ-CP – Nghị định 87/2020/NĐ-CP; 07/2025/NĐ-CP – Nghị định số 07/2025/NĐ-CP ngày 09/01/2025 của Chính phủ sửa đổi, bổ sung một số điều của các Nghị định trong lĩnh vực hộ tịch, quốc tịch, chứng thực.; 106/2021/TT-BTC – Thông tư 106/2021/TT-BTC; 60/2014/QH13 – Luật 60/2014/QH13; 52/2014/QH13 – Luật Hôn nhân và gia đình 52/2014/QH13; 04/2024/TT-BTP – Sửa đổi, bổ sung một số điều của Thông tư số 02/2020/TT-BTP ngày 08/4/2020 của Bộ trưởng Bộ Tư pháp ban hành, hướng dẫn sử dụng, quản lý mẫu sổ quốc tịch và mẫu giấy tờ về quốc tịch và Thông tư số 04/2020/TT-BTP ngày 28/5/2020 của Bộ trưởng Bộ Tư pháp quy định chi tiết thi hành một số điều của Luật Hộ tịch và Nghị định số 123/2015/NĐ-CP ngày 15/11/2015 của Chính phủ quy định chi tiết một số điều và biện pháp thi hành Luật Hộ tịch; 123/2015/NĐ-CP – Nghị định 123/2015/NĐ-CP; Thông tư số 281/2016/TT-BTC – quy định mức thu, chế độ thu, nộp, quản lý và sử dụng phí khai thác, sử dụng thông tin trong cơ sở dữ liệu hộ tịch, phí xác nhận có quốc tịch Việt Nam, phí xác nhận là người gốc Việt Nam, lệ phí quốc tịch | |
| ☐ | conditions | - Công dân Việt Nam thường trú tại địa bàn xã ở khu vực biên giới đăng ký kết hôn với công dân của nước láng giềng thường trú tại đơn vị hành chính tương đương cấp xã của Việt Nam tiếp giáp với xã ở khu vực biên giới của Việt Nam nơi công dân Việt Nam thường trú. - Nam từ đủ 20 tuổi trở lên, nữ từ đ | |

Verifier: ______  Date: ______  Result: ☐ all correct  ☐ corrected (see notes)

## 2. 1.000689 — Thủ tục đăng ký khai sinh kết hợp đăng ký nhận cha, mẹ, con

- Source: [Thủ tục đăng ký khai sinh kết hợp đăng ký nhận cha, mẹ, con](https://moj.gov.vn/portal/thu-tuc-hanh-chinh/chi-tiet-1.000689.html) · `moj-portal#1.000689` · locator moj.gov.vn TTHC chi tiết mã 1.000689; cơ quan theo 1833/QĐ-BTP Phần I, mục A.7 (https://cdn.haiphong.gov.vn/gov-hpg/6855/tintuc/2025/11/1833638988795114181791.pdf) · retrieved 2026-10-10 · effective _null_
- Record file: `data/processed/moj/1.000689.json`

| ✓ | Field | Value in record | Correction / note |
|---|---|---|---|
| ☐ | title | Thủ tục đăng ký khai sinh kết hợp đăng ký nhận cha, mẹ, con | |
| ☐ | variant_of | 1.001193 | |
| ☐ | field | Hộ tịch | |
| ☐ | level | cấp xã | |
| ☐ | jurisdiction | toàn quốc | |
| ☐ | receiving_agency | UBND cấp xã | |
| ☐ | channels | Qua bưu chính công ích; Trực tuyến; Trực tiếp | |
| ☐ | required_documents[1] | Tờ khai đăng ký nhận cha, mẹ, con theo mẫu; · SL 2 (Số bản chính: 1; Số bản sao: 1) · bắt buộc _null_ | |
| ☐ | required_documents[2] | Hộ chiếu/Thẻ căn cước công dân/Thẻ căn cước/Căn cước điện tử/Giấy chứng nhận căn cước hoặc các giấy tờ khác có dán ảnh và thông tin cá nhân do cơ quan có thẩm quyền cấp, còn giá trị sử dụng (sau đây gọi tắt là giấy tờ tùy thân) để chứng minh về nhân thân khi làm thủ tục trực tiếp tại cơ quan đăng ký hộ tịch. · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents[3] | Bản chính Giấy chứng sinh; trường hợp không có Giấy chứng sinh thì nộp văn bản của người làm chứng xác nhận về việc sinh; nếu không có người làm chứng thì phải có giấy cam đoan về việc sinh; · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents[4] | Giấy tờ có giá trị chứng minh thông tin về cư trú trong trường hợp cơ quan đăng ký hộ tịch không thể khai thác được thông tin về nơi cư trú của công dân theo các phương thức quy định tại khoản 2 Điều 14 Nghị định số 104/2022/NĐ-CP ngày 21/12/2022 của Chính phủ. Trường hợp các thông tin về giấy tờ chứng minh nơi cư trú đã được khai thác từ Cơ sở dữ liệu quốc gia về dân cư bằng các phương thức này thì người có yêu cầu không phải xuất trình (theo hình thức trực tiếp) hoặc tải lên (theo hình thức trực tuyến). · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents[5] | Trường hợp không có văn bản nêu trên thì phải có văn bản cam đoan của các bên nhận cha, mẹ, con về mối quan hệ cha, mẹ, con và có ít nhất hai người làm chứng về mối quan hệ cha, mẹ, con. · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents[6] | Tờ khai đăng ký khai sinh theo mẫu; · SL 2 (Số bản chính: 1; Số bản sao: 1) · bắt buộc _null_ | |
| ☐ | required_documents[7] | Văn bản của cơ quan y tế, cơ quan giám định hoặc cơ quan khác có thẩm quyền xác nhận quan hệ cha con, quan hệ mẹ con. · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents — none missing vs source | 7 items | |
| ☐ | fees[1] | theo HĐND tỉnh · Mức lệ phí cụ thể do Hội đồng nhân dân tỉnh, thành phố trực thuộc Trung ương quyết định · theo tỉnh | |
| ☐ | fees[2] | miễn lệ phí · người thuộc gia đình có công với cách mạng; người thuộc hộ nghèo; người khuyết tật · toàn quốc | |
| ☐ | fees[3] | theo Thông tư số 281/2016/TT-BTC · Phí cấp bản sao Giấy khai sinh, bản sao Trích lục đăng ký nhận cha, mẹ, con (nếu có yêu cầu) thực hiện theo quy định tại Thông tư số 281/2016/TT-BTC ngày 14/11/2016 của Bộ Tài chính · toàn quốc | |
| ☐ | processing_time | Qua bưu chính công ích, Trực tuyến: 03 ngày làm việc, trường hợp cần phải xác minh không quá 08 ngày làm việc; Trực tiếp: 03 ngày làm việc, trường hợp phải xác minh thì không quá 08 ngày làm việc. | |
| ☐ | steps (count) | 5 | |
| ☐ | legal_basis | 60/2014/QH13 – Luật 60/2014/QH13; 85/2019/TT-BTC – Thông tư 85/2019/TT-BTC; 123/2015/NĐ-CP – Nghị định 123/2015/NĐ-CP; 66.7/2025/NQ-CP; 106/2021/TT-BTC – Thông tư 106/2021/TT-BTC; 07/2025/NĐ-CP – Nghị định số 07/2025/NĐ-CP ngày 09/01/2025 của Chính phủ sửa đổi, bổ sung một số điều của các Nghị định trong lĩnh vực hộ tịch, quốc tịch, chứng thực.; 18/2026/NĐ-CP – Sửa đổi, bổ sung một số nghị định để cắt giảm, đơn giản hóa thủ tục hành chính, điều kiện kinh doanh thuộc phạm vi quản lý của Bộ Tư pháp; 52/2014/QH13 – Luật Hôn nhân và gia đình 52/2014/QH13; 04/2020/TT-BTP – Thông tư 04/2020/TT-BTP; 01/2022/TT-BTP – Thông tư sửa đổi; 87/2020/NĐ-CP – Nghị định 87/2020/NĐ-CP; 08/2025/TT-BTP – Thông tư số 08/2025/TT-BTP ngày 12/6/2025 của Bộ trưởng Bộ Tư pháp quy định về phân định thẩm quyền của chính quyền địa phương 02 cấp và phân cấp trong lĩnh vực quản lý nhà nước của Bộ Tư pháp; 104/2022/NĐ-CP – Nghị định sửa đổi, bổ sung một số điều của các nghị định liên quan đến việc nộp, xuất trình sổ hộ khẩu, sổ tạm trú giấy khi thực hiện thủ tục hành chính, cung cấp dịch vụ công; 04/2024/TT-BTP – Sửa đổi, bổ sung một số điều của Thông tư số 02/2020/TT-BTP ngày 08/4/2020 của Bộ trưởng Bộ Tư pháp ban hành, hướng dẫn sử dụng, quản lý mẫu sổ quốc tịch và mẫu giấy tờ về quốc tịch và Thông tư số 04/2020/TT-BTP ngày 28/5/2020 của Bộ trưởng Bộ Tư pháp quy định chi tiết thi hành một số điều của Luật Hộ tịch và Nghị định số 123/2015/NĐ-CP ngày 15/11/2015 của Chính phủ quy định chi tiết một số điều và biện pháp thi hành Luật Hộ tịch; Thông tư số 281/2016/TT-BTC – quy định mức thu, chế độ thu, nộp, quản lý và sử dụng phí khai thác, sử dụng thông tin trong cơ sở dữ liệu hộ tịch, phí xác nhận có quốc tịch Việt Nam, phí xác nhận là người gốc Việt Nam, lệ phí quốc tịch; 120/2025/NĐ-CP – Nghị định số 120/2025/NĐ-CP ngày 11/6/2025 của Chính phủ quy định về phân định thẩm quyền của chính quyền địa phương 02 cấp trong lĩnh vực quản lý nhà nước của Bộ Tư pháp. | |
| ☐ | conditions | - Bên nhận và bên được nhận là cha, mẹ, con đều còn sống; - Việc nhận cha, mẹ, con không có tranh chấp.  - Trường hợp nam, nữ chung sống với nhau như vợ chồng, không đăng ký kết hôn, sinh con, người con sống cùng với người cha, khi người cha làm thủ tục nhận con mà không liên hệ được với người mẹ th | |

Verifier: ______  Date: ______  Result: ☐ all correct  ☐ corrected (see notes)

## 3. 1.000757 — Cấp lại thẻ căn cước (thực hiện tại cấp trung ương)

- Source: [Cấp lại thẻ căn cước (thực hiện tại cấp trung ương) — Cổng Dịch vụ công Bộ Công an](https://dichvucong.bocongan.gov.vn/bocongan/bothutuc/tthc?matt=26096) · `bca-portal#1.000757` · locator _null_ · retrieved 2026-10-10 · effective _null_
- Record file: `data/processed/bca-portal/1.000757.json`

| ✓ | Field | Value in record | Correction / note |
|---|---|---|---|
| ☐ | title | Cấp lại thẻ căn cước (thực hiện tại cấp trung ương) | |
| ☐ | variant_of | _null_ | |
| ☐ | field | Cấp, quản lý căn cước | |
| ☐ | level | trung ương | |
| ☐ | jurisdiction | toàn quốc | |
| ☐ | receiving_agency | Cục cảnh sát quản lý hành chính về trật tự, xã hội | |
| ☐ | channels | Trực tiếp; Trực tuyến | |
| ☐ | required_documents[1] | Phiếu đề nghị giải quyết thủ tục về căn cước (Mẫu DC02 ban hành kèm theo Thông tư số 17/2024/TT-BCA của Bộ Công an) · SL 1 (Bản chính: 1; Bản sao: 0) · bắt buộc _null_ · ghi chú: Nhóm hồ sơ: Phiếu này là biểu mẫu điện tử, công dân kê khai đối với trường hợp nộp hồ sơ trực tuyến / Mẫu: Mẫu DC02 Phiếu đề nghị giải quyết thủ tục về căn cước.doc | |
| ☐ | required_documents[2] | Giấy tờ, tài liệu có giá trị pháp lý chứng minh là người đại diện hợp pháp của người dưới 14 tuổi · SL 1 (Bản chính: 1; Bản sao: 0) · bắt buộc _null_ · ghi chú: Nhóm hồ sơ: Trường hợp người đề nghị cấp, cấp đổi, cấp lại thẻ căn cước là người đại diện hợp pháp của người dưới 14 tuổi thì hồ sơ đề nghị cấp, cấp đổi, cấp lại thẻ căn cước phải có giấy tờ, tài liệu có giá trị pháp lý chứng minh là người đại diện hợp pháp của người dưới 14 tuổi. | |
| ☐ | required_documents[3] | Phiếu thu nhận thông tin căn cước (Mẫu CC01 ban hành kèm theo Thông tư số 17/2024/TT-BCA của Bộ Công an) · SL 1 (Bản chính: 1; Bản sao: 0) · bắt buộc _null_ · ghi chú: Nhóm hồ sơ: Phiếu được tạo lập khi trích xuất thông tin của công dân trong Cơ sở dữ liệu quốc gia về dân cư và in trong quá trình thu nhận hồ sơ căn cước để công dân kiểm tra và ký xác nhận. / Mẫu: Mẫu CC01 Phiếu thu nhận thông tin căn cước.doc | |
| ☐ | required_documents — none missing vs source | 3 items | |
| ☐ | fees | _null_ | |
| ☐ | processing_time | Trực tiếp: 07 Ngày làm việc; Trực tuyến: 07 Ngày làm việc | |
| ☐ | steps (count) | 7 | |
| ☐ | legal_basis | Luật Căn cước Số: 26/2023/QH15; Nghị định của Chính phủ: Quy định chi tiết một số điều và biện pháp thi hành Luật Căn cước Số: 70/2024/NĐ-CP; Thông tư 16/2024/TT-BCA quy định về mẫu thẻ căn cước, mẫu giấy chứng nhận căn cước Số: 16/2024/TT-BCA; Thông tư quy định chi tiết một số điều và biện pháp thi hành Luật Căn cước Số: 17/2024/TT-BCA; Thông tư quy định quy định về quy trình cấp, cấp đổi, cấp lại thẻ căn cước, giấy chứng nhận căn cước Số: 18/2024/TT-BCA | |
| ☐ | conditions | Không. | |

Verifier: ______  Date: ______  Result: ☐ all correct  ☐ corrected (see notes)

## 4. 1.000889 — Cấp đổi thẻ căn cước (thực hiện tại cấp trung ương)

- Source: [Cấp đổi thẻ căn cước (thực hiện tại cấp trung ương) — Cổng Dịch vụ công Bộ Công an](https://dichvucong.bocongan.gov.vn/bocongan/bothutuc/tthc?matt=26099) · `bca-portal#1.000889` · locator _null_ · retrieved 2026-10-10 · effective _null_
- Record file: `data/processed/bca-portal/1.000889.json`

| ✓ | Field | Value in record | Correction / note |
|---|---|---|---|
| ☐ | title | Cấp đổi thẻ căn cước (thực hiện tại cấp trung ương) | |
| ☐ | variant_of | _null_ | |
| ☐ | field | Cấp, quản lý căn cước | |
| ☐ | level | trung ương | |
| ☐ | jurisdiction | toàn quốc | |
| ☐ | receiving_agency | Cục cảnh sát quản lý hành chính về trật tự, xã hội | |
| ☐ | channels | Trực tiếp | |
| ☐ | required_documents[1] | Giấy tờ, tài liệu có giá trị pháp lý chứng minh là người đại diện hợp pháp của người dưới 14 tuổi · SL 1 (Bản chính: 1; Bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents[2] | Phiếu thu nhận thông tin căn cước (Mẫu CC01 ban hành kèm theo Thông tư số 17/2024/TT-BCA của Bộ Công an) · SL 1 (Bản chính: 1; Bản sao: 0) · bắt buộc _null_ · ghi chú: Nhóm hồ sơ: Phiếu được tạo lập khi trích xuất thông tin của công dân trong Cơ sở dữ liệu quốc gia về dân cư và in trong quá trình thu nhận hồ sơ căn cước để công dân kiểm tra và ký xác nhận. / Mẫu: Mẫu CC01 Phiếu thu nhận thông tin căn cước.doc | |
| ☐ | required_documents — none missing vs source | 2 items | |
| ☐ | fees[1] | miễn lệ phí · Lệ phí: trang ghi "Không" · toàn quốc | |
| ☐ | processing_time | Trực tiếp: 07 Ngày làm việc | |
| ☐ | steps (count) | 6 | |
| ☐ | legal_basis | Luật Căn cước Số: 26/2023/QH15; Thông tư quy định chi tiết một số điều và biện pháp thi hành Luật Căn cước Số: 17/2024/TT-BCA; Nghị định của Chính phủ: Quy định chi tiết một số điều và biện pháp thi hành Luật Căn cước Số: 70/2024/NĐ-CP; Thông tư 16/2024/TT-BCA quy định về mẫu thẻ căn cước, mẫu giấy chứng nhận căn cước Số: 16/2024/TT-BCA; Thông tư quy định quy định về quy trình cấp, cấp đổi, cấp lại thẻ căn cước, giấy chứng nhận căn cước Số: 18/2024/TT-BCA | |
| ☐ | conditions | Không. | |

Verifier: ______  Date: ______  Result: ☐ all correct  ☐ corrected (see notes)

## 5. 1.001669 — Thủ tục đăng ký giám hộ có yếu tố nước ngoài

- Source: [Thủ tục đăng ký giám hộ có yếu tố nước ngoài](https://moj.gov.vn/portal/thu-tuc-hanh-chinh/chi-tiet-1.001669.html) · `moj-portal#1.001669` · locator moj.gov.vn TTHC chi tiết mã 1.001669; cơ quan theo 1833/QĐ-BTP Phần I, mục A.20 (https://cdn.haiphong.gov.vn/gov-hpg/6855/tintuc/2025/11/1833638988795114181791.pdf) · retrieved 2026-10-10 · effective _null_
- Record file: `data/processed/moj/1.001669.json`

| ✓ | Field | Value in record | Correction / note |
|---|---|---|---|
| ☐ | title | Thủ tục đăng ký giám hộ có yếu tố nước ngoài | |
| ☐ | variant_of | 1.004837 | |
| ☐ | field | Hộ tịch | |
| ☐ | level | cấp xã | |
| ☐ | jurisdiction | toàn quốc | |
| ☐ | receiving_agency | UBND cấp xã | |
| ☐ | channels | Trực tiếp; Qua bưu chính công ích; Trực tuyến | |
| ☐ | required_documents[1] | Văn bản cử người giám hộ theo quy định của Bộ luật Dân sự đối với trường hợp đăng ký giám hộ cử; giấy tờ chứng minh điều kiện giám hộ đương nhiên theo quy định của Bộ luật Dân sự đối với trường hợp đăng ký giám hộ đương nhiên; trường hợp có nhiều người cùng đủ điều kiện làm giám hộ đương nhiên thì nộp thêm văn bản thỏa thuận về việc cử một người làm giám hộ đương nhiên; · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents[2] | Mẫu hộ tịch điện tử tương tác đăng ký giám hộ (do người yêu cầu cung cấp thông tin theo hướng dẫn trên Cổng dịch vụ công nếu người có yêu cầu lựa chọn nộp hồ sơ theo hình thức trực tuyến); · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents[3] | Giấy tờ có giá trị chứng minh thông tin về cư trú trong trường hợp cơ quan đăng ký hộ tịch không thể khai thác được thông tin về nơi cư trú của công dân theo các phương thức quy định tại khoản 2 Điều 14 Nghị định số 104/2022/NĐ-CP ngày 21/12/2022 của Chính phủ. Trường hợp các thông tin về giấy tờ chứng minh nơi cư trú đã được khai thác từ Cơ sở dữ liệu quốc gia về dân cư bằng các phương thức này thì người có yêu cầu không phải xuất trình (theo hình thức trực tiếp) hoặc tải lên (theo hình thức trực tuyến). · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents[4] | Tờ khai đăng ký giám hộ theo mẫu (nếu người yêu cầu lựa chọn nộp hồ sơ theo hình thức trực tiếp hoặc gửi hồ sơ qua hệ thống bưu chính); · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents[5] | Hộ chiếu/Thẻ căn cước công dân/Thẻ căn cước/Căn cước điện tử/Giấy chứng nhận căn cước hoặc các giấy tờ khác có dán ảnh và thông tin cá nhân do cơ quan có thẩm quyền cấp, còn giá trị sử dụng (sau đây gọi tắt là giấy tờ tùy thân) để chứng minh về nhân thân khi làm thủ tục trực tiếp tại cơ quan đăng ký hộ tịch. · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents[6] | Văn bản ủy quyền (được chứng thực) theo quy định của pháp luật trong trường hợp ủy quyền thực hiện đăng ký giám hộ. Trường hợp người được ủy quyền là ông, bà, cha, mẹ, con, vợ, chồng, anh, chị, em ruột của người ủy quyền thì văn bản ủy quyền không phải chứng thực. · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents — none missing vs source | 6 items | |
| ☐ | fees[1] | theo HĐND tỉnh · Mức lệ phí cụ thể do Hội đồng nhân dân tỉnh, thành phố trực thuộc Trung ương quyết định · theo tỉnh | |
| ☐ | fees[2] | miễn lệ phí · người thuộc gia đình có công với cách mạng; người thuộc hộ nghèo; người khuyết tật · toàn quốc | |
| ☐ | fees[3] | theo Thông tư số 281/2016/TT-BTC · Phí cấp bản sao Trích lục đăng ký giám hộ (nếu có yêu cầu) thực hiện theo quy định tại Thông tư số 281/2016/TT-BTC ngày 14/11/2016 của Bộ Tài chính · toàn quốc | |
| ☐ | processing_time | 05 ngày làm việc đối với việc đăng ký giám hộ cử, 03 ngày làm việc đối với việc đăng ký giám hộ đương nhiên. | |
| ☐ | steps (count) | 5 | |
| ☐ | legal_basis | 60/2014/QH13 – Luật 60/2014/QH13; 106/2021/TT-BTC – Thông tư 106/2021/TT-BTC; 01/2022/TT-BTP – Thông tư sửa đổi; 08/2025/TT-BTP – Thông tư số 08/2025/TT-BTP ngày 12/6/2025 của Bộ trưởng Bộ Tư pháp quy định về phân định thẩm quyền của chính quyền địa phương 02 cấp và phân cấp trong lĩnh vực quản lý nhà nước của Bộ Tư pháp; 120/2025/NĐ-CP – Nghị định số 120/2025/NĐ-CP ngày 11/6/2025 của Chính phủ quy định về phân định thẩm quyền của chính quyền địa phương 02 cấp trong lĩnh vực quản lý nhà nước của Bộ Tư pháp.; 87/2020/NĐ-CP – Nghị định 87/2020/NĐ-CP; 66.7/2025/NQ-CP; 85/2019/TT-BTC – Thông tư 85/2019/TT-BTC; 04/2024/TT-BTP – Sửa đổi, bổ sung một số điều của Thông tư số 02/2020/TT-BTP ngày 08/4/2020 của Bộ trưởng Bộ Tư pháp ban hành, hướng dẫn sử dụng, quản lý mẫu sổ quốc tịch và mẫu giấy tờ về quốc tịch và Thông tư số 04/2020/TT-BTP ngày 28/5/2020 của Bộ trưởng Bộ Tư pháp quy định chi tiết thi hành một số điều của Luật Hộ tịch và Nghị định số 123/2015/NĐ-CP ngày 15/11/2015 của Chính phủ quy định chi tiết một số điều và biện pháp thi hành Luật Hộ tịch; 07/2025/NĐ-CP – Nghị định số 07/2025/NĐ-CP ngày 09/01/2025 của Chính phủ sửa đổi, bổ sung một số điều của các Nghị định trong lĩnh vực hộ tịch, quốc tịch, chứng thực.; 123/2015/NĐ-CP – Nghị định 123/2015/NĐ-CP; Thông tư số 281/2016/TT-BTC – quy định mức thu, chế độ thu, nộp, quản lý và sử dụng phí khai thác, sử dụng thông tin trong cơ sở dữ liệu hộ tịch, phí xác nhận có quốc tịch Việt Nam, phí xác nhận là người gốc Việt Nam, lệ phí quốc tịch; 18/2026/NĐ-CP – Sửa đổi, bổ sung một số nghị định để cắt giảm, đơn giản hóa thủ tục hành chính, điều kiện kinh doanh thuộc phạm vi quản lý của Bộ Tư pháp; 91/2015/QH13 – Bộ luật dân sự; 04/2020/TT-BTP – Thông tư 04/2020/TT-BTP; 104/2022/NĐ-CP – Nghị định sửa đổi, bổ sung một số điều của các nghị định liên quan đến việc nộp, xuất trình sổ hộ khẩu, sổ tạm trú giấy khi thực hiện thủ tục hành chính, cung cấp dịch vụ công | |
| ☐ | conditions | - Việc giám hộ giữa công dân Việt Nam và người nước ngoài cùng cư trú tại Việt Nam. - Cá nhân có đủ các điều kiện sau đây có thể làm người giám hộ: + Có năng lực hành vi dân sự đầy đủ. + Có tư cách đạo đức tốt và các điều kiện cần thiết để thực hiện quyền, nghĩa vụ của người giám hộ. + Không phải là | |

Verifier: ______  Date: ______  Result: ☐ all correct  ☐ corrected (see notes)

## 6. 1.001695 — Thủ tục đăng ký khai sinh kết hợp đăng ký nhận cha, mẹ, con có yếu tố nước ngoài

- Source: [Thủ tục đăng ký khai sinh kết hợp đăng ký nhận cha, mẹ, con có yếu tố nước ngoài](https://moj.gov.vn/portal/thu-tuc-hanh-chinh/chi-tiet-1.001695.html) · `moj-portal#1.001695` · locator moj.gov.vn TTHC chi tiết mã 1.001695; cơ quan theo 1833/QĐ-BTP Phần I, mục A.8 (https://cdn.haiphong.gov.vn/gov-hpg/6855/tintuc/2025/11/1833638988795114181791.pdf) · retrieved 2026-10-10 · effective _null_
- Record file: `data/processed/moj/1.001695.json`

| ✓ | Field | Value in record | Correction / note |
|---|---|---|---|
| ☐ | title | Thủ tục đăng ký khai sinh kết hợp đăng ký nhận cha, mẹ, con có yếu tố nước ngoài | |
| ☐ | variant_of | 1.001193 | |
| ☐ | field | Hộ tịch | |
| ☐ | level | cấp xã | |
| ☐ | jurisdiction | toàn quốc | |
| ☐ | receiving_agency | UBND cấp xã | |
| ☐ | channels | Qua bưu chính công ích; Trực tuyến; Trực tiếp | |
| ☐ | required_documents[1] | Giấy tờ có giá trị chứng minh thông tin về cư trú trong trường hợp cơ quan đăng ký hộ tịch không thể khai thác được thông tin về nơi cư trú của công dân theo các phương thức quy định tại khoản 2 Điều 14 Nghị định số 104/2022/NĐ-CP ngày 21/12/2022 của Chính phủ. Trường hợp các thông tin về giấy tờ chứng minh nơi cư trú đã được khai thác từ Cơ sở dữ liệu quốc gia về dân cư bằng các phương thức này thì người có yêu cầu không phải xuất trình (theo hình thức trực tiếp) hoặc tải lên (theo hình thức trực tuyến). · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents[2] | Trường hợp trẻ em sinh ra tại nước ngoài thì nộp Giấy chứng sinh hoặc giấy tờ khác do cơ quan có thẩm quyền nước ngoài cấp xác nhận về việc trẻ em được sinh ra ở nước ngoài và quan hệ mẹ - con (nếu có); · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents[3] | Trường hợp cha hoặc mẹ hoặc cả cha, mẹ là người nước ngoài thì phải nộp văn bản thỏa thuận của cha, mẹ về việc lựa chọn quốc tịch cho con. Trường hợp cha, mẹ lựa chọn quốc tịch nước ngoài cho con, thì ngoài văn bản thỏa thuận lựa chọn quốc tịch còn phải có xác nhận của cơ quan có thẩm quyền nước mà trẻ được chọn mang quốc tịch về việc trẻ có quốc tịch phù hợp quy định của pháp luật nước đó. · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents[4] | Tờ khai đăng ký khai sinh theo mẫu; · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents[5] | Hộ chiếu/Thẻ căn cước công dân/Thẻ căn cước/Căn cước điện tử/Giấy chứng nhận căn cước hoặc các giấy tờ khác có dán ảnh và thông tin cá nhân do cơ quan có thẩm quyền cấp, còn giá trị sử dụng (sau đây gọi tắt là giấy tờ tùy thân) để chứng minh về nhân thân khi làm thủ tục trực tiếp tại cơ quan đăng ký hộ tịch. · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents[6] | Giấy chứng sinh · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents[7] | Tờ khai đăng ký nhận cha, mẹ, con theo mẫu; · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents[8] | Trường hợp trẻ em sinh ra ở nước ngoài, có cha hoặc mẹ là công dân Việt Nam hoặc cha và mẹ đều là công dân Việt Nam, chưa được đăng ký khai sinh ở nước ngoài, về cư trú tại Việt Nam thì xuất trình giấy tờ chứng minh việc trẻ em đã nhập cảnh hợp pháp vào Việt Nam (như: hộ chiếu, giấy tờ có giá trị đi lại quốc tế có dấu xác nhận nhập cảnh của cơ quan quản lý xuất, nhập cảnh) và văn bản xác nhận của cơ quan công an có thẩm quyền về việc trẻ em đang cư trú tại Việt Nam. · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents[9] | Trường hợp không có Giấy chứng sinh thì nộp văn bản của người làm chứng xác nhận về việc sinh; nếu không có văn bản của người làm chứng thì phải có giấy cam đoan về việc sinh. · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents[10] | Trường hợp đăng ký nhận cha, mẹ, con giữa công dân Việt Nam với người nước ngoài hoặc giữa người nước ngoài với nhau thì người nước ngoài phải nộp bản sao hộ chiếu hoặc giấy tờ có giá trị thay hộ chiếu để chứng minh về nhân thân. · SL 1 (Số bản chính: 0; Số bản sao: 1) · bắt buộc _null_ | |
| ☐ | required_documents[11] | Văn bản của cơ quan y tế, cơ quan giám định hoặc cơ quan, tổ chức khác có thẩm quyền ở trong nước hoặc nước ngoài xác nhận quan hệ cha con, quan hệ mẹ con. · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents — none missing vs source | 11 items | |
| ☐ | fees[1] | theo HĐND tỉnh · Mức lệ phí cụ thể do Hội đồng nhân dân tỉnh, thành phố trực thuộc Trung ương quyết định · theo tỉnh | |
| ☐ | fees[2] | miễn lệ phí · người thuộc gia đình có công với cách mạng; người thuộc hộ nghèo; người khuyết tật · toàn quốc | |
| ☐ | fees[3] | theo Thông tư số 281/2016/TT-BTC · Phí cấp bản sao Giấy khai sinh, bản sao Trích lục đăng ký nhận cha, mẹ, con (nếu có yêu cầu) thực hiện theo quy định tại Thông tư số 281/2016/TT-BTC ngày 14/11/2016 của Bộ Tài chính · toàn quốc | |
| ☐ | processing_time | 10 | |
| ☐ | steps (count) | 5 | |
| ☐ | legal_basis | 04/2024/TT-BTP – Sửa đổi, bổ sung một số điều của Thông tư số 02/2020/TT-BTP ngày 08/4/2020 của Bộ trưởng Bộ Tư pháp ban hành, hướng dẫn sử dụng, quản lý mẫu sổ quốc tịch và mẫu giấy tờ về quốc tịch và Thông tư số 04/2020/TT-BTP ngày 28/5/2020 của Bộ trưởng Bộ Tư pháp quy định chi tiết thi hành một số điều của Luật Hộ tịch và Nghị định số 123/2015/NĐ-CP ngày 15/11/2015 của Chính phủ quy định chi tiết một số điều và biện pháp thi hành Luật Hộ tịch; 04/2020/TT-BTP – Thông tư 04/2020/TT-BTP; 85/2019/TT-BTC – Thông tư 85/2019/TT-BTC; 08/2025/TT-BTP – Thông tư số 08/2025/TT-BTP ngày 12/6/2025 của Bộ trưởng Bộ Tư pháp quy định về phân định thẩm quyền của chính quyền địa phương 02 cấp và phân cấp trong lĩnh vực quản lý nhà nước của Bộ Tư pháp; 123/2015/NĐ-CP – Nghị định 123/2015/NĐ-CP; 18/2026/NĐ-CP – Sửa đổi, bổ sung một số nghị định để cắt giảm, đơn giản hóa thủ tục hành chính, điều kiện kinh doanh thuộc phạm vi quản lý của Bộ Tư pháp; 52/2014/QH13 – Luật Hôn nhân và gia đình 52/2014/QH13; 120/2025/NĐ-CP – Nghị định số 120/2025/NĐ-CP ngày 11/6/2025 của Chính phủ quy định về phân định thẩm quyền của chính quyền địa phương 02 cấp trong lĩnh vực quản lý nhà nước của Bộ Tư pháp.; 60/2014/QH13 – Luật 60/2014/QH13; Thông tư số 281/2016/TT-BTC – quy định mức thu, chế độ thu, nộp, quản lý và sử dụng phí khai thác, sử dụng thông tin trong cơ sở dữ liệu hộ tịch, phí xác nhận có quốc tịch Việt Nam, phí xác nhận là người gốc Việt Nam, lệ phí quốc tịch; 07/2025/NĐ-CP – Nghị định số 07/2025/NĐ-CP ngày 09/01/2025 của Chính phủ sửa đổi, bổ sung một số điều của các Nghị định trong lĩnh vực hộ tịch, quốc tịch, chứng thực.; 104/2022/NĐ-CP – Nghị định sửa đổi, bổ sung một số điều của các nghị định liên quan đến việc nộp, xuất trình sổ hộ khẩu, sổ tạm trú giấy khi thực hiện thủ tục hành chính, cung cấp dịch vụ công; 66.7/2025/NQ-CP; 106/2021/TT-BTC – Thông tư 106/2021/TT-BTC | |
| ☐ | conditions | - Bên nhận và bên được nhận là cha, mẹ, con đều còn sống; - Việc nhận cha, mẹ, con không có tranh chấp. | |

Verifier: ______  Date: ______  Result: ☐ all correct  ☐ corrected (see notes)

## 7. 1.002755 — Gia hạn tạm trú

- Source: [Gia hạn tạm trú — Cổng Dịch vụ công Bộ Công an](https://dichvucong.bocongan.gov.vn/bocongan/bothutuc/tthc?matt=26345) · `bca-portal#1.002755` · locator _null_ · retrieved 2026-10-10 · effective _null_
- Record file: `data/processed/bca-portal/1.002755.json`

| ✓ | Field | Value in record | Correction / note |
|---|---|---|---|
| ☐ | title | Gia hạn tạm trú | |
| ☐ | variant_of | _null_ | |
| ☐ | field | Đăng ký, quản lý cư trú | |
| ☐ | level | cấp xã | |
| ☐ | jurisdiction | toàn quốc | |
| ☐ | receiving_agency | Công an Xã | |
| ☐ | channels | Trực tiếp; Trực tuyến | |
| ☐ | required_documents[1] | - Tờ khai thay đổi thông tin cư trú (Mẫu CT01 ban hành kèm theo Thông tư số 56/2021/TT-BCA); đối với người gia hạn tạm trú là người chưa thành niên thì trong tờ khai phải ghi rõ ý kiến đồng ý của cha, mẹ hoặc người giám hộ, trừ trường hợp đã có ý kiến đồng ý bằng văn bản; · SL 1 (Bản chính: 1; Bản sao: 0) · bắt buộc _null_ · ghi chú: Nhóm hồ sơ: * Hồ sơ gia hạn tạm trú gồm: / Mẫu: CT01 Tờ khai thay đổi thông tin cư trú.doc | |
| ☐ | required_documents[2] | - Giấy tờ, tài liệu chứng minh chỗ ở hợp pháp. · SL 1 (Bản chính: 1; Bản sao: 0) · bắt buộc _null_ · ghi chú: Nhóm hồ sơ: * Hồ sơ gia hạn tạm trú gồm: | |
| ☐ | required_documents[3] | - Tờ khai thay đổi thông tin cư trú (Mẫu CT01 ban hành kèm theo Thông tư số 56/2021/TT-BCA); · SL 1 (Bản chính: 1; Bản sao: 0) · bắt buộc _null_ · ghi chú: Nhóm hồ sơ: * Gia hạn tạm trú tại nơi đơn vị đóng quân trong Công an nhân dân, hồ sơ gồm: | |
| ☐ | required_documents[4] | - Giấy giới thiệu của Thủ trưởng đơn vị quản lý trực tiếp ghi rõ nội dung để làm thủ tục gia hạn tạm trú và đơn vị có chỗ ở cho cán bộ chiến sĩ (ký tên, đóng dấu). · SL 1 (Bản chính: 1; Bản sao: 0) · bắt buộc _null_ · ghi chú: Nhóm hồ sơ: * Gia hạn tạm trú tại nơi đơn vị đóng quân trong Công an nhân dân, hồ sơ gồm: | |
| ☐ | required_documents[5] | - Tờ khai thay đổi thông tin cư trú (của từng người) (Mẫu CT01 ban hành kèm theo Thông tư số 56/2021/TT-BCA); · SL 1 (Bản chính: 1; Bản sao: 0) · bắt buộc _null_ · ghi chú: Nhóm hồ sơ: * Gia hạn tạm trú theo danh sách, hồ sơ gồm: / Mẫu: CT01 Tờ khai thay đổi thông tin cư trú.doc | |
| ☐ | required_documents[6] | - Văn bản đề nghị gia hạn tạm trú trong đó ghi rõ thông tin về chỗ ở hợp pháp kèm danh sách người gia hạn tạm trú. Danh sách bao gồm những thông tin cơ bản của từng người: họ, chữ đệm và tên; ngày, tháng, năm sinh; giới tính; số định danh cá nhân và thời hạn tạm trú. · SL 1 (Bản chính: 1; Bản sao: 0) · bắt buộc _null_ · ghi chú: Nhóm hồ sơ: * Gia hạn tạm trú theo danh sách, hồ sơ gồm: | |
| ☐ | required_documents — none missing vs source | 6 items | |
| ☐ | fees[1] | miễn phí · Phí: trang ghi "Không" · toàn quốc | |
| ☐ | fees[2] | miễn lệ phí · Lệ phí: trang ghi "Không" · toàn quốc | |
| ☐ | processing_time | Trực tiếp: 03 Ngày làm việc; Trực tuyến: 03 Ngày làm việc | |
| ☐ | steps (count) | 5 | |
| ☐ | legal_basis | Luật 68/2020/QH14 Số: 68/2020/QH14; Thông tư 55/2021/TT-BCA Số: 55/2021/TT-BCA; Thông tư 56/2021/TT-BCA Số: 56/2021/TT-BCA; Thông tư 57/2021/TT-BCA Số: 57/2021/TT-BCA | |
| ☐ | conditions | Trong thời hạn 15 ngày trước ngày kết thúc thời hạn tạm trú đã đăng ký, công dân phải làm thủ tục gia hạn tạm trú. | |

Verifier: ______  Date: ______  Result: ☐ all correct  ☐ corrected (see notes)

## 8. 2.000513 — Thủ tục đăng ký lại kết hôn có yếu tố nước ngoài

- Source: [Thủ tục đăng ký lại kết hôn có yếu tố nước ngoài](https://moj.gov.vn/portal/thu-tuc-hanh-chinh/chi-tiet-2.000513.html) · `moj-portal#2.000513` · locator moj.gov.vn TTHC chi tiết mã 2.000513; cơ quan theo 1833/QĐ-BTP Phần I, mục A.14 (https://cdn.haiphong.gov.vn/gov-hpg/6855/tintuc/2025/11/1833638988795114181791.pdf) · retrieved 2026-10-10 · effective _null_
- Record file: `data/processed/moj/2.000513.json`

| ✓ | Field | Value in record | Correction / note |
|---|---|---|---|
| ☐ | title | Thủ tục đăng ký lại kết hôn có yếu tố nước ngoài | |
| ☐ | variant_of | 1.000894 | |
| ☐ | field | Hộ tịch | |
| ☐ | level | cấp xã | |
| ☐ | jurisdiction | toàn quốc | |
| ☐ | receiving_agency | UBND cấp xã | |
| ☐ | channels | Qua bưu chính công ích; Trực tuyến; Trực tiếp | |
| ☐ | required_documents[1] | Tờ khai đăng ký lại kết hôn theo mẫu (nếu người có yêu cầu lựa chọn nộp hồ sơ theo hình thức trực tiếp); · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents[2] | Giấy tờ có giá trị chứng minh thông tin về cư trú trong trường hợp cơ quan đăng ký hộ tịch không thể khai thác được thông tin về nơi cư trú của công dân theo các phương thức quy định tại khoản 2 Điều 14 Nghị định số 104/2022/NĐ-CP ngày 21/12/2022 của Chính phủ. Trường hợp các thông tin về giấy tờ chứng minh nơi cư trú đã được khai thác từ Cơ sở dữ liệu quốc gia về dân cư bằng các phương thức này thì người có yêu cầu không phải xuất trình (theo hình thức trực tiếp) hoặc tải lên (theo hình thức trực tuyến). · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents[3] | Hộ chiếu/Thẻ căn cước công dân/Thẻ căn cước/Căn cước điện tử/Giấy chứng nhận căn cước hoặc các giấy tờ khác có dán ảnh và thông tin cá nhân do cơ quan có thẩm quyền cấp, còn giá trị sử dụng (sau đây gọi tắt là giấy tờ tùy thân) để chứng minh về nhân thân khi làm thủ tục trực tiếp tại cơ quan đăng ký hộ tịch. · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents[4] | Bản sao Giấy chứng nhận kết hôn được cấp trước đây. Nếu không có bản sao Giấy chứng nhận kết hôn thì nộp bản sao hồ sơ, giấy tờ cá nhân có các thông tin liên quan đến nội dung đăng ký kết hôn. · SL 1 (Số bản chính: 0; Số bản sao: 1) · bắt buộc _null_ | |
| ☐ | required_documents[5] | Mẫu hộ tịch điện tử tương tác đăng ký lại kết hôn · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents — none missing vs source | 5 items | |
| ☐ | fees[1] | theo HĐND tỉnh · Mức lệ phí cụ thể do Hội đồng nhân dân tỉnh, thành phố trực thuộc Trung ương quyết định · theo tỉnh | |
| ☐ | fees[2] | miễn lệ phí · người thuộc gia đình có công với cách mạng; người thuộc hộ nghèo; người khuyết tật · toàn quốc | |
| ☐ | processing_time | 05 ngày làm việc; trường hợp phải xác minh thì thời hạn giải quyết không quá 25 ngày. | |
| ☐ | steps (count) | 13 | |
| ☐ | legal_basis | 106/2021/TT-BTC – Thông tư 106/2021/TT-BTC; 85/2019/TT-BTC – Thông tư 85/2019/TT-BTC; 08/2025/TT-BTP – Thông tư số 08/2025/TT-BTP ngày 12/6/2025 của Bộ trưởng Bộ Tư pháp quy định về phân định thẩm quyền của chính quyền địa phương 02 cấp và phân cấp trong lĩnh vực quản lý nhà nước của Bộ Tư pháp; 120/2025/NĐ-CP – Nghị định số 120/2025/NĐ-CP ngày 11/6/2025 của Chính phủ quy định về phân định thẩm quyền của chính quyền địa phương 02 cấp trong lĩnh vực quản lý nhà nước của Bộ Tư pháp.; 123/2015/NĐ-CP – Nghị định 123/2015/NĐ-CP - Quy định chi tiết một số điều và biện pháp thi hành Luật Hộ tịch; 60/2014/QH13 – Luật 60/2014/QH13; 66.7/2025/NQ-CP; 07/2025/NĐ-CP – Nghị định số 07/2025/NĐ-CP ngày 09/01/2025 của Chính phủ sửa đổi, bổ sung một số điều của các Nghị định trong lĩnh vực hộ tịch, quốc tịch, chứng thực.; 52/2014/QH13 – Luật Hôn nhân và gia đình 52/2014/QH13; 104/2022/NĐ-CP – Nghị định sửa đổi, bổ sung một số điều của các nghị định liên quan đến việc nộp, xuất trình sổ hộ khẩu, sổ tạm trú giấy khi thực hiện thủ tục hành chính, cung cấp dịch vụ công; 04/2020/TT-BTP – Thông tư 04/2020/TT-BTP; 87/2020/NĐ-CP – Nghị định 87/2020/NĐ-CP; 04/2024/TT-BTP – Sửa đổi, bổ sung một số điều của Thông tư số 02/2020/TT-BTP ngày 08/4/2020 của Bộ trưởng Bộ Tư pháp ban hành, hướng dẫn sử dụng, quản lý mẫu sổ quốc tịch và mẫu giấy tờ về quốc tịch và Thông tư số 04/2020/TT-BTP ngày 28/5/2020 của Bộ trưởng Bộ Tư pháp quy định chi tiết thi hành một số điều của Luật Hộ tịch và Nghị định số 123/2015/NĐ-CP ngày 15/11/2015 của Chính phủ quy định chi tiết một số điều và biện pháp thi hành Luật Hộ tịch; Thông tư số 03/2023/TT-BTP – Thông tư số 03/2023/TT-BTP ngày 02/8/2023 của Bộ trưởng Bộ Tư pháp; 18/2026/NĐ-CP – Sửa đổi, bổ sung một số nghị định để cắt giảm, đơn giản hóa thủ tục hành chính, điều kiện kinh doanh thuộc phạm vi quản lý của Bộ Tư pháp; 01/2022/TT-BTP – Thông tư sửa đổi; Thông tư số 281/2016/TT-BTC – quy định mức thu, chế độ thu, nộp, quản lý và sử dụng phí khai thác, sử dụng thông tin trong cơ sở dữ liệu hộ tịch, phí xác nhận có quốc tịch Việt Nam, phí xác nhận là người gốc Việt Nam, lệ phí quốc tịch | |
| ☐ | conditions | - Việc kết hôn đã được đăng ký tại cơ quan có thẩm quyền của Việt Nam trước ngày 01/01/2016 nhưng Sổ đăng ký kết hôn và bản chính Giấy chứng nhận kết hôn đều bị mất. - Cả hai bên yêu cầu đăng ký lại kết hôn còn sống vào thời điểm yêu cầu đăng ký lại kết hôn. | |

Verifier: ______  Date: ______  Result: ☐ all correct  ☐ corrected (see notes)

## 9. 2.000756 — Thủ tục đăng ký chấm dứt giám hộ có yếu tố nước ngoài

- Source: [Thủ tục đăng ký chấm dứt giám hộ có yếu tố nước ngoài](https://moj.gov.vn/portal/thu-tuc-hanh-chinh/chi-tiet-2.000756.html) · `moj-portal#2.000756` · locator moj.gov.vn TTHC chi tiết mã 2.000756; cơ quan theo 1833/QĐ-BTP Phần I, mục A.22 (https://cdn.haiphong.gov.vn/gov-hpg/6855/tintuc/2025/11/1833638988795114181791.pdf) · retrieved 2026-10-10 · effective _null_
- Record file: `data/processed/moj/2.000756.json`

| ✓ | Field | Value in record | Correction / note |
|---|---|---|---|
| ☐ | title | Thủ tục đăng ký chấm dứt giám hộ có yếu tố nước ngoài | |
| ☐ | variant_of | 1.004845 | |
| ☐ | field | Hộ tịch | |
| ☐ | level | cấp xã | |
| ☐ | jurisdiction | toàn quốc | |
| ☐ | receiving_agency | UBND cấp xã | |
| ☐ | channels | Trực tiếp; Qua bưu chính công ích; Trực tuyến | |
| ☐ | required_documents[1] | Tờ khai đăng ký chấm dứt giám hộ theo mẫu (nếu người có yêu cầu lựa chọn nộp hồ sơ theo hình thức trực tiếp); · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents[2] | Văn bản ủy quyền (được chứng thực) theo quy định của pháp luật trong trường hợp ủy quyền thực hiện đăng ký chấm dứt giám hộ. Trường hợp người được ủy quyền là ông, bà, cha, mẹ, con, vợ, chồng, anh, chị, em ruột của người ủy quyền thì văn bản ủy quyền không phải chứng thực. · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents[3] | Hộ chiếu/Thẻ căn cước công dân/Thẻ căn cước/Căn cước điện tử/Giấy chứng nhận căn cước hoặc các giấy tờ khác có dán ảnh và thông tin cá nhân do cơ quan có thẩm quyền cấp, còn giá trị sử dụng (sau đây gọi tắt là giấy tờ tùy thân) để chứng minh về nhân thân khi làm thủ tục trực tiếp tại cơ quan đăng ký hộ tịch. · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents[4] | Mẫu hộ tịch điện tử tương tác đăng ký chấm dứt giám hộ (do người yêu cầu cung cấp thông tin theo hướng dẫn trên Cổng dịch vụ công, nếu người có yêu cầu lựa chọn nộp hồ sơ theo hình thức trực tuyến) · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents[5] | Giấy tờ làm căn cứ chấm dứt giám hộ theo quy định của Bộ luật Dân sự. · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents[6] | Giấy tờ có giá trị chứng minh thông tin về cư trú trong trường hợp cơ quan đăng ký hộ tịch không thể khai thác được thông tin về nơi cư trú của công dân theo các phương thức quy định tại khoản 2 Điều 14 Nghị định số 104/2022/NĐ-CP ngày 21/12/2022 của Chính phủ. Trường hợp các thông tin về giấy tờ chứng minh nơi cư trú đã được khai thác từ Cơ sở dữ liệu quốc gia về dân cư bằng các phương thức này thì người có yêu cầu không phải xuất trình (theo hình thức trực tiếp) hoặc tải lên (theo hình thức trực tuyến). · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents — none missing vs source | 6 items | |
| ☐ | fees[1] | theo HĐND tỉnh · Mức lệ phí cụ thể do Hội đồng nhân dân tỉnh, thành phố trực thuộc Trung ương quyết định · theo tỉnh | |
| ☐ | fees[2] | miễn lệ phí · người thuộc gia đình có công với cách mạng; người thuộc hộ nghèo; người khuyết tật · toàn quốc | |
| ☐ | fees[3] | theo Thông tư số 281/2016/TT-BTC · Phí cấp bản sao Trích lục đăng ký chấm dứt giám hộ (nếu có yêu cầu) thực hiện theo quy định tại Thông tư số 281/2016/TT-BTC ngày 14/11/2016 của Bộ Tài chính · toàn quốc | |
| ☐ | processing_time | 2 | |
| ☐ | steps (count) | 5 | |
| ☐ | legal_basis | 07/2025/NĐ-CP – Nghị định số 07/2025/NĐ-CP ngày 09/01/2025 của Chính phủ sửa đổi, bổ sung một số điều của các Nghị định trong lĩnh vực hộ tịch, quốc tịch, chứng thực.; 66.7/2025/NQ-CP; Thông tư số 281/2016/TT-BTC – quy định mức thu, chế độ thu, nộp, quản lý và sử dụng phí khai thác, sử dụng thông tin trong cơ sở dữ liệu hộ tịch, phí xác nhận có quốc tịch Việt Nam, phí xác nhận là người gốc Việt Nam, lệ phí quốc tịch; 04/2020/TT-BTP – Thông tư 04/2020/TT-BTP; 87/2020/NĐ-CP – Nghị định 87/2020/NĐ-CP; 01/2022/TT-BTP – Thông tư sửa đổi; 106/2021/TT-BTC – Thông tư 106/2021/TT-BTC; 60/2014/QH13 – Luật 60/2014/QH13; 104/2022/NĐ-CP – Nghị định sửa đổi, bổ sung một số điều của các nghị định liên quan đến việc nộp, xuất trình sổ hộ khẩu, sổ tạm trú giấy khi thực hiện thủ tục hành chính, cung cấp dịch vụ công; Thông tư số 03/2023/TT-BTP – Thông tư số 03/2023/TT-BTP ngày 02/8/2023 của Bộ trưởng Bộ Tư pháp; 123/2015/NĐ-CP – Nghị định 123/2015/NĐ-CP; 120/2025/NĐ-CP – Nghị định số 120/2025/NĐ-CP ngày 11/6/2025 của Chính phủ quy định về phân định thẩm quyền của chính quyền địa phương 02 cấp trong lĩnh vực quản lý nhà nước của Bộ Tư pháp.; 91/2015/QH13 – Bộ luật dân sự; 85/2019/TT-BTC – Thông tư 85/2019/TT-BTC; 04/2024/TT-BTP – Sửa đổi, bổ sung một số điều của Thông tư số 02/2020/TT-BTP ngày 08/4/2020 của Bộ trưởng Bộ Tư pháp ban hành, hướng dẫn sử dụng, quản lý mẫu sổ quốc tịch và mẫu giấy tờ về quốc tịch và Thông tư số 04/2020/TT-BTP ngày 28/5/2020 của Bộ trưởng Bộ Tư pháp quy định chi tiết thi hành một số điều của Luật Hộ tịch và Nghị định số 123/2015/NĐ-CP ngày 15/11/2015 của Chính phủ quy định chi tiết một số điều và biện pháp thi hành Luật Hộ tịch; 08/2025/TT-BTP – Thông tư số 08/2025/TT-BTP ngày 12/6/2025 của Bộ trưởng Bộ Tư pháp quy định về phân định thẩm quyền của chính quyền địa phương 02 cấp và phân cấp trong lĩnh vực quản lý nhà nước của Bộ Tư pháp; 18/2026/NĐ-CP – Sửa đổi, bổ sung một số nghị định để cắt giảm, đơn giản hóa thủ tục hành chính, điều kiện kinh doanh thuộc phạm vi quản lý của Bộ Tư pháp | |
| ☐ | conditions | Không | |

Verifier: ______  Date: ______  Result: ☐ all correct  ☐ corrected (see notes)

## 10. 2.002189 — Thủ tục ghi vào Sổ hộ tịch việc kết hôn của công dân Việt Nam đã được giải quyết tại cơ quan có thẩm quyền của nước ngoài

- Source: [Thủ tục ghi vào Sổ hộ tịch việc kết hôn của công dân Việt Nam đã được giải quyết tại cơ quan có thẩm quyền của nước ngoài](https://moj.gov.vn/portal/thu-tuc-hanh-chinh/chi-tiet-2.002189.html) · `moj-portal#2.002189` · locator moj.gov.vn TTHC chi tiết mã 2.002189; cơ quan theo 1833/QĐ-BTP Phần I, mục A.27 (https://cdn.haiphong.gov.vn/gov-hpg/6855/tintuc/2025/11/1833638988795114181791.pdf) · retrieved 2026-10-10 · effective _null_
- Record file: `data/processed/moj/2.002189.json`

| ✓ | Field | Value in record | Correction / note |
|---|---|---|---|
| ☐ | title | Thủ tục ghi vào Sổ hộ tịch việc kết hôn của công dân Việt Nam đã được giải quyết tại cơ quan có thẩm quyền của nước ngoài | |
| ☐ | variant_of | 1.000894 | |
| ☐ | field | Hộ tịch | |
| ☐ | level | cấp xã | |
| ☐ | jurisdiction | toàn quốc | |
| ☐ | receiving_agency | UBND cấp xã | |
| ☐ | channels | Qua bưu chính công ích; Trực tiếp; Trực tuyến | |
| ☐ | required_documents[1] | Giấy tờ có giá trị chứng minh thông tin về cư trú trong trường hợp cơ quan đăng ký hộ tịch không thể khai thác được thông tin về nơi cư trú của công dân theo các phương thức quy định tại khoản 2 Điều 14 Nghị định số 104/2022/NĐ-CP ngày 21/12/2022 của Chính phủ. Trường hợp các thông tin về giấy tờ chứng minh nơi cư trú đã được khai thác từ Cơ sở dữ liệu quốc gia về dân cư bằng các phương thức này thì người có yêu cầu không phải xuất trình (theo hình thức trực tiếp) hoặc tải lên (theo hình thức trực tuyến). · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents[2] | Mẫu hộ tịch điện tử tương tác ghi vào Sổ hộ tịch việc kết hôn (do người yêu cầu cung cấp thông tin theo hướng dẫn trên Cổng dịch vụ công, nếu người có yêu cầu lựa chọn nộp hồ sơ theo hình thức trực tuyến) · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents[3] | Hộ chiếu/Thẻ căn cước công dân/Thẻ căn cước/Căn cước điện tử/Giấy chứng nhận căn cước hoặc các giấy tờ khác có dán ảnh và thông tin cá nhân do cơ quan có thẩm quyền cấp, còn giá trị sử dụng (sau đây gọi tắt là giấy tờ tùy thân) để chứng minh về nhân thân khi làm thủ tục trực tiếp tại cơ quan đăng ký hộ tịch. · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents[4] | Văn bản ủy quyền (được chứng thực) theo quy định của pháp luật trong trường hợp ủy quyền thực hiện việc ghi chú kết hôn. Trường hợp người được ủy quyền là ông, bà, cha, mẹ, con, vợ, chồng, anh, chị, em ruột của người ủy quyền thì văn bản ủy quyền không phải chứng thực. · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents[5] | Nếu công dân Việt Nam đã ly hôn hoặc hủy việc kết hôn tại cơ quan có thẩm quyền nước ngoài thì phải nộp Trích lục về việc đã ghi vào Sổ hộ tịch việc ly hôn hoặc hủy việc kết hôn (Trích lục ghi chú ly hôn). · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents[6] | Tờ khai ghi chú kết hôn theo mẫu (nếu người có yêu cầu lựa chọn nộp hồ sơ theo hình thức trực tiếp hoặc gửi hồ sơ qua hệ thống bưu chính); · SL 1 (Số bản chính: 1; Số bản sao: 0) · bắt buộc _null_ | |
| ☐ | required_documents[7] | Bản sao giấy tờ chứng nhận việc kết hôn do cơ quan có thẩm quyền của nước ngoài cấp; · SL 1 (Số bản chính: 0; Số bản sao: 1) · bắt buộc _null_ | |
| ☐ | required_documents — none missing vs source | 7 items | |
| ☐ | fees[1] | theo HĐND tỉnh · Mức lệ phí cụ thể do Hội đồng nhân dân tỉnh, thành phố trực thuộc Trung ương quyết định · theo tỉnh | |
| ☐ | fees[2] | miễn lệ phí · người thuộc gia đình có công với cách mạng; người thuộc hộ nghèo; người khuyết tật · toàn quốc | |
| ☐ | fees[3] | theo Thông tư số 281/2016/TT-BTC · Phí cấp bản sao Trích lục ghi chú kết hôn (nếu có yêu cầu) thực hiện theo quy định tại Thông tư số 281/2016/TT-BTC ngày 14/11/2016 của Bộ Tài chính · toàn quốc | |
| ☐ | processing_time | 05 ngày làm việc, trường hợp phải xác minh thì thời hạn giải quyết không quá 08 ngày làm việc. | |
| ☐ | steps (count) | 5 | |
| ☐ | legal_basis | Thông tư số 03/2023/TT-BTP – Thông tư số 03/2023/TT-BTP ngày 02/8/2023 của Bộ trưởng Bộ Tư pháp; 66.7/2025/NQ-CP; 04/2024/TT-BTP – Sửa đổi, bổ sung một số điều của Thông tư số 02/2020/TT-BTP ngày 08/4/2020 của Bộ trưởng Bộ Tư pháp ban hành, hướng dẫn sử dụng, quản lý mẫu sổ quốc tịch và mẫu giấy tờ về quốc tịch và Thông tư số 04/2020/TT-BTP ngày 28/5/2020 của Bộ trưởng Bộ Tư pháp quy định chi tiết thi hành một số điều của Luật Hộ tịch và Nghị định số 123/2015/NĐ-CP ngày 15/11/2015 của Chính phủ quy định chi tiết một số điều và biện pháp thi hành Luật Hộ tịch; 106/2021/TT-BTC – Thông tư 106/2021/TT-BTC; Luật số 52/2014/QH13 – Hôn nhân và gia đình; 120/2025/NĐ-CP – Nghị định số 120/2025/NĐ-CP ngày 11/6/2025 của Chính phủ quy định về phân định thẩm quyền của chính quyền địa phương 02 cấp trong lĩnh vực quản lý nhà nước của Bộ Tư pháp.; 08/2025/TT-BTP – Thông tư số 08/2025/TT-BTP ngày 12/6/2025 của Bộ trưởng Bộ Tư pháp quy định về phân định thẩm quyền của chính quyền địa phương 02 cấp và phân cấp trong lĩnh vực quản lý nhà nước của Bộ Tư pháp; Luật số 60/2014/QH13 – Hộ tịch; Thông tư số 281/2016/TT-BTC – quy định mức thu, chế độ thu, nộp, quản lý và sử dụng phí khai thác, sử dụng thông tin trong cơ sở dữ liệu hộ tịch, phí xác nhận có quốc tịch Việt Nam, phí xác nhận là người gốc Việt Nam, lệ phí quốc tịch; 07/2025/NĐ-CP – Nghị định số 07/2025/NĐ-CP ngày 09/01/2025 của Chính phủ sửa đổi, bổ sung một số điều của các Nghị định trong lĩnh vực hộ tịch, quốc tịch, chứng thực.; Nghị định số123/2015/NĐ-CP – Quy định chi tiết một số điều và biện pháp thi hành Luật Hộ tịch; 01/2022/TT-BTP – Thông tư sửa đổi; 18/2026/NĐ-CP – Sửa đổi, bổ sung một số nghị định để cắt giảm, đơn giản hóa thủ tục hành chính, điều kiện kinh doanh thuộc phạm vi quản lý của Bộ Tư pháp; 04/2020/TT-BTP – Thông tư 04/2020/TT-BTP; 104/2022/NĐ-CP – Nghị định sửa đổi, bổ sung một số điều của các nghị định liên quan đến việc nộp, xuất trình sổ hộ khẩu, sổ tạm trú giấy khi thực hiện thủ tục hành chính, cung cấp dịch vụ công; 85/2019/TT-BTC – Thông tư 85/2019/TT-BTC; 87/2020/NĐ-CP – Nghị định 87/2020/NĐ-CP | |
| ☐ | conditions | - Việc kết hôn giữa công dân Việt Nam với nhau hoặc với người nước ngoài đã được giải quyết tại cơ quan có thẩm quyền của nước ngoài ở nước ngoài được ghi vào Sổ hộ tịch nếu tại thời điểm kết hôn, các bên đáp ứng đủ điều kiện kết hôn và không vi phạm điều cấm theo quy định của Luật Hôn nhân và gia đ | |

Verifier: ______  Date: ______  Result: ☐ all correct  ☐ corrected (see notes)

## Summary

| Records checked | Fields checked | Fields wrong | Records fully correct |
|---|---|---|---|
| | | | |
