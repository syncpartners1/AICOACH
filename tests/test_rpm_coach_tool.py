from pathlib import Path
import json, re, subprocess
ROOT=Path(__file__).resolve().parents[1]

def data(html,name,end):
    raw=html.split('const '+name+' = ',1)[1].split(end,1)[0].strip().removesuffix(';')
    return json.loads(raw)

def test_rpm_tool_is_original_optional_and_not_a_new_meeting():
    html=(ROOT/'autogpt/coaching/session_maps.html').read_text()
    tracks=data(html,'COACHING_TRACKS','const ROUTING_ENTRIES')
    aid=next(t for t in tracks if t['id']=='coach_aids')['sessions'][-1]
    assert aid['num']=='כלי 12' and 'לא מפגש נוסף' in aid['phase']
    assert len(aid['lanes'])==3 and 'Tony Robbins' in aid['goal']
    assert 'לא כלי רשמי' in aid['goal']
    assert all(lane['mins']=={'60':'—','45':'—','30':'—'} for lane in aid['lanes'])
    assert 'המשמעות היא הסיבה האישית' in json.dumps(aid,ensure_ascii=False)
    assert 'resultPurposeLink' in html and 'openResultPurposeTool' in html

def test_rpm_addition_has_no_new_client_inputs_or_writes():
    html=(ROOT/'autogpt/coaching/session_maps.html').read_text()
    modal=html.split('id="resultPurposeModal"',1)[1].split('MASTER ROUTING MODAL',1)[0]
    assert '<input' not in modal and '<textarea' not in modal
    function=html.split('function openResultPurposeTool()',1)[1].split('function renderReactionDock()',1)[0]
    for marker in ['fetch(', 'localStorage','sessionStorage','logMetric','logAction']:
        assert marker not in function

def test_rpm_keeps_base_session_order_times_and_five_lanes():
    html=(ROOT/'autogpt/coaching/session_maps.html').read_text()
    tracks=data(html,'COACHING_TRACKS','const ROUTING_ENTRIES')
    personal=next(t for t in tracks if t['id']=='personal')
    for num in ['P-07','P-08']:
        session=next(s for s in personal['sessions'] if s['num']==num)
        assert len(session['lanes'])==5
    assert 'יובילו אותך בהכרח אל היעד' not in next(s for s in personal['sessions'] if s['num']=='P-08')['lanes'][2]['prompts']


def test_all_original_tracks_sessions_lane_order_and_minutes_unchanged():
    import hashlib
    html=(ROOT/'autogpt/coaching/session_maps.html').read_text()
    tracks=data(html,'COACHING_TRACKS','const ROUTING_ENTRIES')
    fingerprint=[{'id':t['id'],'sessions':[{'num':s['num'],'lanes':[{'title':l['title'],'mins':l['mins']} for l in s['lanes']]} for s in t['sessions'] if s['num']!='כלי 12']} for t in tracks]
    assert hashlib.sha256(json.dumps(fingerprint,sort_keys=True,ensure_ascii=False).encode()).hexdigest()=='bd2fec1908b8e457989cb51193de448aafadacca8d4a93c7fa87fb17d4a7298b'
