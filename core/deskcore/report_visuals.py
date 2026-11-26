"""Honor selective visual choices and repair only selected missing image links."""
import re

IMAGE = re.compile(r'!\[[^\]]*\]\(([^\s)]+)\)')


def reference(visual):
    match = re.fullmatch(r'(figure|table)-(\d+)-p\d+', visual.get('id', ''))
    if not match:
        return None
    prefix = r'(?:图|Fig(?:ure)?\.?)' if match[1] == 'figure' else r'(?:表|Table)'
    return re.compile(prefix+r'\s*'+match[2]+r'(?!\d)', re.I)


def attach(report):
    """Idempotent, bilingual, no API calls; retain existing narrative and usage."""
    sections = report.get('report_sections', [])
    attachments = []
    plan={p.get('id'):p for p in report.get('visual_plan',[]) if isinstance(p,dict) and isinstance(p.get('id'),str) and p.get('decision') in ('embed','omit') and isinstance(p.get('reason'),str) and p['reason'].strip()} if isinstance(report.get('visual_plan'),list) else {}
    for visual in report.get('visuals', []):
        ref = reference(visual)
        url = visual.get('url', '')
        if not ref or not re.fullmatch(r'/paper-assets/[a-f0-9]{20}/(?:figure|table)-\d+-p\d+\.png', url):
            continue
        choice=plan.get(visual['id'],{})
        if choice.get('decision')=='omit':
            for section in sections:
                for field in ('markdown','markdown_en'):
                    if field in section:section[field]=re.sub(r'!\[[^\]]*\]\('+re.escape(url)+r'\)', '',section[field]).strip()
            continue
        existing = next((s for s in sections if url in IMAGE.findall(s.get('markdown', ''))), None)
        chosen=next((s for s in sections if s.get('part')==choice.get('part') and type(choice.get('part')) is int and 1<=choice['part']<=8),None)
        if existing is None and not (choice.get('decision')=='embed' and chosen is not None):
            # No plan and no Chinese image means no selection, not an omission to fix.
            continue
        candidates = [s for s in sections if s.get('part', 9) <= 8]
        if not candidates:
            continue
        target = existing or chosen
        for field, english in [('markdown', False), ('markdown_en', True)]:
            if field not in target or not target[field]:
                continue
            if any(url in IMAGE.findall(s.get(field, '')) for s in sections):
                continue
            label = visual.get('label', visual['id'])
            alt = f"{label} · PDF {'page' if english else '第'} {visual['page']}{'' if english else ' 页'}"
            insertion = f'![{alt}]({url})'
            blocks = target[field].split('\n\n')
            match_index = next((i for i, b in enumerate(blocks) if ref.search(b) and not b.lstrip().startswith('#')), None)
            if match_index is None:
                caption = visual.get('caption', '').replace('\n', ' ')
                insertion += '\n\n' + ('Original caption: ' if english else '原文图注：') + caption
                blocks.append(insertion)
            else:
                blocks.insert(match_index+1, insertion)
            target[field] = '\n\n'.join(blocks)
            attachments.append({'id':visual['id'], 'part':target['part'], 'language':'en' if english else 'zh'})
        # Once a figure is present, remove only a precise stale unavailable notice.
        number = re.search(r'-(\d+)-p', visual['id'])[1]
        if visual['kind'] == 'figure':
            for section in sections:
                for field in ('markdown','markdown_en'):
                    if field not in section:continue
                    section[field] = re.sub(r'该原图暂未能展示，请查看原文图\s*'+number+r'(?!\d)[。.]?', '', section[field])
                    section[field] = re.sub(r'The original figure cannot be displayed here; please see Figure\s+'+number+r'(?!\d)'+r' in the original (?:paper|text)\.', '', section[field], flags=re.I)
    report['visual_attachments']=[a for a in report.get('visual_attachments',[]) if plan.get(a.get('id'),{}).get('decision')!='omit']
    if attachments:
        report.setdefault('visual_attachments', []).extend(attachments)
    report['visual_check'] = {'available':len(report.get('visuals', [])), 'embedded_zh':len(set(u for s in sections for u in IMAGE.findall(s.get('markdown','')))), 'embedded_en':len(set(u for s in sections for u in IMAGE.findall(s.get('markdown_en',''))))}
    if sections:
        report['main_idea'] = sections[0]['markdown']
    return report
