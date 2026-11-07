"""Recognize an explicit calendar return only when both fiscal overrides are blank."""
import re

def calendar_period(master, picture, rows, ein, year, url):
    trusted = [r for r in rows if float(r[2]) >= .95]
    compact = lambda s: re.sub(r'\s+', '', s).casefold()
    if not any(master.canonical_ein_digits(r[1]) == master.canonical_ein_digits(ein) for r in trusted):
        return {}
    if not any('returnoforganizationexemptfromincometax' in compact(r[1]) for r in trusted):
        return {}
    if not any(r[1].strip() == str(year) for r in trusted):
        return {}
    beginnings = [r for r in trusted if re.fullmatch(r'a?forthe'+str(year)+r'calendaryear,?ortaxyearbeginning', compact(r[1]))]
    endings = [r for r in trusted if compact(r[1]) == 'andending']
    if len(beginnings) != 1 or len(endings) != 1:
        return {}
    a, b = beginnings[0], endings[0]
    bounds = lambda r: (min(p[0] for p in r[0]), min(p[1] for p in r[0]), max(p[0] for p in r[0]), max(p[1] for p in r[0]))
    aa, bb = bounds(a), bounds(b)
    if abs((aa[1]+aa[3])-(bb[1]+bb[3])) > 8 or bb[0]-aa[2] < picture.width*.06:
        return {}
    # The field row spans the form, whose right margin mirrors its left margin.
    # Inspect actual pixels: absence of an OCR value alone is never blank proof.
    top, bottom = int(max(aa[1],bb[1])), int(min(aa[3],bb[3]))-1
    right = int(picture.width-aa[0])
    if bottom-top < 7 or right-bb[2] < picture.width*.08:
        return {}
    for left, end in [(int(aa[2])+3,int(bb[0])-3),(int(bb[2])+3,right-3)]:
        with picture.crop((left,top,end,bottom)).convert('L') as crop:
            # Allow isolated scan specks, but no connected glyph-sized mark.
            pixels = crop.load(); dark = {(x,y) for x in range(crop.width) for y in range(crop.height) if pixels[x,y] < 170}
            while dark:
                todo=[dark.pop()]; count=0
                while todo:
                    x,y=todo.pop(); count+=1
                    if count>=4: return {}
                    for p in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                        if p in dark: dark.remove(p); todo.append(p)
    return dict(ein=master.canonical_ein_digits(ein),tax_year_label=year,
                period_begin=f'{year}-01-01',period_end=f'{year}-12-31',source_url=url,
                period_extraction='Scanned IRS calendar header with pixel-verified blank fiscal fields')
