from pathlib import Path
from io import BytesIO
import re
import argparse
from xml.sax.saxutils import escape
from PIL import Image as PILImage
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
import pypdfium2 as pdfium

BASE=Path(__file__).resolve().parent
WORK=BASE.parents[2]
OUT=BASE
QA=WORK/'tmp'/'manual'/'rendered'
OUT.mkdir(parents=True,exist_ok=True);QA.mkdir(parents=True,exist_ok=True)
pdfmetrics.registerFont(TTFont('CN','C:/Windows/Fonts/msyh.ttc',subfontIndex=0))
pdfmetrics.registerFont(TTFont('CNBold','C:/Windows/Fonts/msyhbd.ttc',subfontIndex=0))
W,H=A4; M=40; CW=W-2*M
TEXT='#22282C';ACCENT='#2B625B'
styles={
 'body':ParagraphStyle('body',fontName='CN',fontSize=10,leading=16,textColor=HexColor(TEXT),wordWrap='CJK'),
 'step':ParagraphStyle('step',fontName='CNBold',fontSize=12,leading=18,textColor=HexColor(TEXT),wordWrap='CJK'),
 'note':ParagraphStyle('note',fontName='CN',fontSize=9,leading=14,textColor=HexColor(ACCENT),wordWrap='CJK'),
 'caption':ParagraphStyle('caption',fontName='CN',fontSize=8,leading=12,textColor=HexColor('#70787C'),alignment=1,wordWrap='CJK')}
# Crop to the relevant controls; pixel coordinates refer to the original screenshots.
IMAGES={
 'login.png':((475,390,1180,840),350),
 'teacher-register.png':((475,250,1180,975),350),
 'student-register.png':((475,200,1180,1025),350),
 'teacher-class-entry.png':((0,0,1650,385),155),
 'teacher-class-dialog.png':((458,463,1184,813),220),
 'teacher-new-entry.png':((0,0,1650,460),145),
 'teacher-create-complete.png':((422,218,1604,1274),310),
 'teacher-publish.png':((422,260,1605,1274),255),
 'teacher-queue.png':((80,0,1630,540),100),
 'teacher-review-filled.png':((1017,380,1630,1255),300),
 'teacher-process-conversation.png':((1287,382,2074,1430),385),
 'teacher-process-changes.png':((85,380,2075,1150),215),
 'teacher-process-compare.png':((1287,650,2075,1040),190),
 'teacher-reflection-review.png':((1318,670,2045,1010),150),
 'student-open-assignment.png':((0,0,1650,625),175),
 'student-open-existing.png':((0,0,1650,620),195),
 'student-feedback.png':((755,0,1645,440),245),
 'teacher-class.png':((90,8,1240,255),106),
 'teacher-create.png':((560,215,1735,1218),310),
 'teacher-scoring-panel.png':(None,190),
 'teacher-reflection-panel.png':(None,275),
 'teacher-grade.png':((1180,380,1895,1680),475),
 'student-home.png':((150,350,1835,590),82),
 'student-initial.png':((1000,272,1910,1192),275),
 'student-workspace-demo.png':((65,0,1910,1350),430),
 'student-reflection-panel.png':((527,340,1395,1012),305),
 'student-submitted.png':((1010,0,1910,445),175),
}

def para(c,text,y,style='body',gap=8,x=M,width=CW):
 p=Paragraph(escape(text),styles[style]);_,h=p.wrap(width,900)
 p.drawOn(c,x,y-h)
 return y-h-gap

def create(name):
 raw=(BASE/(name+'.md')).read_text(encoding='utf-8')
 title=raw.splitlines()[0][2:]
 pages=re.split(r'^## ',raw,flags=re.M)[1:]
 dest=OUT/(name+'-段落论证.pdf')
 c=canvas.Canvas(str(dest),pagesize=A4)
 c.setTitle(title);c.setAuthor('Right Write');c.setSubject('段落论证作业操作指南')
 for i,page in enumerate(pages,1):
  lines=page.strip().splitlines();ptitle=lines[0]
  c.setFillColor(HexColor(ACCENT));c.rect(M,H-37,25,3,fill=1,stroke=0)
  c.setFont('CN',9);c.drawString(M+35,H-37,title)
  c.setFillColor(HexColor(TEXT));c.setFont('CNBold',21);c.drawString(M,H-75,ptitle)
  y=H-94
  for line in lines[1:]:
   line=line.strip()
   if not line:continue
   if line.startswith('### '): y=para(c,line[4:],y-5,'step',5)
   elif line.startswith('> '):
    y=para(c,line[2:],y-4,'note',8)
   elif line.startswith('!['):
    figures=re.findall(r'!\[(.*?)\]\((.*?)\)',line)
    colw=(CW-16*(len(figures)-1))/len(figures)
    bottoms=[]
    for col,(caption,rel) in enumerate(figures):
     im=PILImage.open(BASE/rel).convert('RGB');crop,mh=IMAGES[Path(rel).name]
     if crop: im=im.crop(crop)
     iw,ih=im.size;scale=min(colw/iw,mh/ih);dw,dh=iw*scale,ih*scale
     from reportlab.lib.utils import ImageReader
     x=M+col*(colw+16)+(colw-dw)/2
     c.drawImage(ImageReader(im),x,y-dh,width=dw,height=dh)
     c.setStrokeColor(HexColor('#DEE3E1'));c.setLineWidth(.4);c.rect(x,y-dh,dw,dh,fill=0,stroke=1)
     bottoms.append(para(c,caption,y-dh-5,'caption',10,x=M+col*(colw+16),width=colw))
    y=min(bottoms)
   else:y=para(c,line,y)
  if y<49:raise ValueError(f'{name} page {i} overflow: bottom {y}')
  c.setStrokeColor(HexColor('#DDE3E0'));c.line(M,40,W-M,40)
  c.setFillColor(HexColor('#7B8584'));c.setFont('CN',7.5)
  c.drawString(M,25,'Right Write  ·  段落论证  |  截图为操作示例，班级与日期以老师通知为准')
  c.drawRightString(W-M,25,f'{i} / {len(pages)}')
  c.showPage()
 c.save()
 pdf=pdfium.PdfDocument(str(dest))
 for i,p in enumerate(pdf):p.render(scale=1.3).to_pil().save(QA/f'{name}-{i+1}.png')
 print(f'{dest} | {len(pdf)} pages | {dest.stat().st_size} bytes')
if __name__ == '__main__':
 parser=argparse.ArgumentParser(description='从手册源文件更新同目录 PDF')
 parser.add_argument('--audience',choices=['teacher','student','all'],default='all')
 audience=parser.parse_args().audience
 for key,name in [('teacher','教师使用手册'),('student','学生使用手册')]:
  if audience in (key,'all'):create(name)
