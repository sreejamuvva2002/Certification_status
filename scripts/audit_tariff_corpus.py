"""Read-only structural/provenance audit; does not verify legal interpretation."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from research_tariffs import norm


def audit(out):
    out=Path(out)
    db=sqlite3.connect((out/'corpus.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
    def rows(kind):
        return [json.loads(r[0]) for r in db.execute('SELECT body FROM records WHERE kind=?',(kind,))]
    errors=[]
    try:
        queries={q['query_id'] for q in rows('queries')}
        docs={d['document_id']:d for d in rows('documents')}
        chunks={c['chunk_id']:c for c in rows('chunks')}
        claims={c['claim_id']:c for c in rows('claims')}
        texts={}
        for docid,d in docs.items():
            path=out/d['text_path']
            if not path.exists():
                errors.append(f'{docid}: missing text file'); continue
            text=path.read_text(encoding='utf-8'); texts[docid]=text
            if hashlib.sha256(text.encode()).hexdigest()!=d['content_hash']:
                errors.append(f'{docid}: content hash mismatch')
            if d['raw_path'] and not (out/d['raw_path']).exists():
                errors.append(f'{docid}: missing downloaded document')
        for chunkid,c in chunks.items():
            if hashlib.sha256(c['text'].encode()).hexdigest()!=c['text_hash']:
                errors.append(f'{chunkid}: chunk hash mismatch')
            if not set(c['query_ids'])<=queries:
                errors.append(f'{chunkid}: unknown query')
            for source in c['sources']:
                text=texts.get(source['document_id'])
                if text is None or text[c['start_char']:c['end_char']]!=c['text']:
                    errors.append(f'{chunkid}: source offsets do not reproduce chunk')
        for cid,c in claims.items():
            chunk=chunks.get(c['chunk_id'])
            if not chunk or norm(c['supporting_excerpt']) not in norm(chunk['text']):
                errors.append(f'{cid}: quote missing from chunk'); continue
            if not set(c['query_ids'])<=set(chunk['query_ids']):
                errors.append(f'{cid}: missing query provenance')
            if c['source_url'] not in {s['url'] for s in chunk['sources']}:
                errors.append(f'{cid}: missing source provenance')
            for name,value in c['fields'].items():
                if value is None: continue
                support=c['field_support'].get(name,'')
                if not support or norm(support) not in norm(chunk['text']) or norm(value).casefold() not in norm(support).casefold():
                    errors.append(f'{cid}: ungrounded field {name}')
        for a in rows('answers'):
            for statement in a['statements']:
                c=claims.get(statement['claim_id'])
                if not c or statement['text']!=c['statement'] or statement['url']!=c['source_url'] or statement['chunk_id']!=c['chunk_id'] or a['query_id'] not in c['query_ids']:
                    errors.append(f"{a['query_id']}: answer citation mismatch")
            if a['selected_claim_ids'] != [s['claim_id'] for s in a['statements']]:
                errors.append(f"{a['query_id']}: selected citation list mismatch")
        for c in rows('candidates'):
            if c['query_id'] not in queries:
                errors.append(f"{c['candidate_id']}: unknown query")
            if c['kept_for_rag'] and c['extraction_status']=='complete' and c['document_id'] not in docs:
                errors.append(f"{c['candidate_id']}: completed candidate missing document")
        return dict(status='passed' if not errors else 'failed',query_count=len(queries),document_count=len(docs),
                    chunk_count=len(chunks),claim_count=len(claims),errors=errors,
                    limitation='Checks stored provenance and structure, not semantic entailment or current legal applicability.')
    finally:
        db.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out',type=Path)
    result=audit(parser.parse_args().out)
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['status']=='passed' else 1)
