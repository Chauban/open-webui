"""生成 pdf-text.test.ts 用的 PDF 样本(需要 fpdf2、Pillow 和 Noto Sans CJK 字体)。

用法:backend/.venv/bin/python src/lib/utils/fixtures/make_pdfs.py src/lib/utils/fixtures
"""

import io, sys
from pathlib import Path
from fpdf import FPDF
from PIL import Image, ImageDraw, ImageFont

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
TTC = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"

# --- 中文三页:页眉「城市更新研究」、页脚「— n —」、段首缩进两字、第一页末段跨页 ---
class Zh(FPDF):
    def header(self):
        self.set_font("noto", size=9); self.cell(0, 8, "城市更新研究", align="C", new_x="LMARGIN", new_y="NEXT"); self.ln(4)
    def footer(self):
        self.set_y(-15); self.set_font("noto", size=9); self.cell(0, 8, f"— {self.page_no()} —", align="C")

pdf = Zh(format="A4"); pdf.set_margins(25, 20, 25)
pdf.add_font("noto", fname=TTC, collection_font_number=2)
pdf.set_auto_page_break(True, margin=25)
pdf.add_page()
pdf.set_font("noto", size=16); pdf.cell(0, 12, "社区参与的文献综述（初稿）", align="C", new_x="LMARGIN", new_y="NEXT"); pdf.ln(4)
pdf.set_font("noto", size=11)
paras = [
    "近二十年来，城市更新研究逐渐从物质空间改造转向社会过程，社区参与成为讨论的核心议题之一。" * 3,
    "已有研究多以个案为主，缺少跨城市的比较视角，对参与效果的评估也不够充分。" * 4,
    "本文梳理了相关文献，按参与主体、参与方式和参与效果三个维度进行归纳，并指出现有研究的不足。" * 18,
    "最后一段讨论未来研究的方向。",
]
for text in paras:
    pdf.multi_cell(0, 7, "　　" + text, new_x="LMARGIN", new_y="NEXT"); pdf.ln(2)
pdf.add_page()
pdf.multi_cell(0, 7, "　　第三页的内容从这里开始，说明研究方法。", new_x="LMARGIN", new_y="NEXT")
pdf.output(str(out / "zh_draft.pdf"))

# --- 英文一页:段间空行、行尾连字符 ---
en = FPDF(format="A4"); en.set_margins(25, 25, 25); en.add_page(); en.set_font("Helvetica", size=11)
en.multi_cell(0, 6, "Urban Renewal and Participation", new_x="LMARGIN", new_y="NEXT"); en.ln(4)
en.multi_cell(0, 6, "Community participation has become a central topic in urban renewal research over the past two decades, and many scholars have examined how residents take part in decision making.", new_x="LMARGIN", new_y="NEXT"); en.ln(5)
line = "Existing studies are mostly single cases, and only a few of them try to compare participa-"
assert 150 < en.get_string_width(line) < 160, en.get_string_width(line)
en.multi_cell(0, 6, line, new_x="LMARGIN", new_y="NEXT")
en.multi_cell(0, 6, "tion across cities and outlines open questions.", new_x="LMARGIN", new_y="NEXT")
en.output(str(out / "en_draft.pdf"))

# --- 混合:一页文字层 + 一页纯图片(扫描页)+ 一页空白 ---
def page_image(text):
    im = Image.new("RGB", (1240, 1754), "white"); d = ImageDraw.Draw(im)
    f = ImageFont.truetype(TTC, 48, index=2)
    for i in range(6): d.text((120, 200 + i * 90), text, fill="black", font=f)
    return im
imgs = [page_image("手写初稿第一页"), page_image("手写初稿第二页")]

mixed = FPDF(format="A4"); mixed.add_font("noto", fname=TTC, collection_font_number=2); mixed.set_font("noto", size=11)
mixed.add_page(); mixed.multi_cell(0, 7, "　　第一页是打出来的文字，可以直接读出来。", new_x="LMARGIN", new_y="NEXT")
mixed.add_page(); buf = io.BytesIO(); imgs[1].save(buf, "PNG"); buf.seek(0); mixed.image(buf, x=0, y=0, w=210)
mixed.add_page()  # 空白页:既没有文字也没有图片
mixed.output(str(out / "mixed.pdf"))
for p in sorted(out.glob("*.pdf")): print(p.name, p.stat().st_size)
