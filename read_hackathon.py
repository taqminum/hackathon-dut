import pdfplumber, pathlib
pdf = pathlib.Path(r'G:\hackathon-dut\大工黑客松S2-赛题发布.pdf')
print('=== HACKATHON PDF ===')
with pdfplumber.open(pdf) as doc:
    for i,page in enumerate(doc.pages[:8]):
        txt = page.extract_text()
        print(f'--- Page {i+1} ---')
        print(txt[:4000] if txt else '[no text]')
