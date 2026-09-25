"""Inspectable Python study plans; metadata mentions are not mastery evidence.

The graph is a project-authored instructional hypothesis, informed by the linked
Python tutorial. Edges do not claim that the Python documentation validates a
universal prerequisite order. No catalogue or learner state is written here.
"""
import re
from ranking import title_family

VERSION = 'python-concepts-v1'
BASE = 'https://docs.python.org/3/tutorial/'


def concept(label, requires, aliases, page, rationale, check):
    return dict(label=label, requires=requires, aliases=aliases, source_url=BASE+page,
                rationale=rationale, self_check=check)


CONCEPTS = {
    'values': concept('Variables and basic values', [], ['variables', 'variable', 'data types', 'strings', 'operators'],
        'introduction.html', 'Named values and simple expressions provide the starting point for the other tasks.',
        'Assign a text value and a number, then explain their types and use them in an expression.'),
    'control': concept('Conditions and loops', ['values'], ['control flow', 'flow control', 'control statements', 'loops', 'looping', 'if/else', 'if statements'],
        'controlflow.html', 'Conditions and repetition operate on values and expressions.',
        'Write a loop that prints only the positive numbers in a short list.'),
    'collections': concept('Lists and dictionaries', ['values'], ['lists', 'list', 'dictionaries', 'dictionary', 'tuples', 'data structures'],
        'datastructures.html', 'Collections organise individual values into structures that can be processed.',
        'Store three named items in a dictionary and retrieve one by its key.'),
    'functions': concept('Functions', ['control'], ['functions', 'function', 'def statement'],
        'controlflow.html#defining-functions', 'This route introduces control flow before packaging behaviour into reusable functions.',
        'Write a function with a parameter and return value; explain how return differs from print.'),
    'files': concept('Reading and writing files', ['control', 'collections'], ['file i/o', 'file handling', 'file input', 'file output', 'reading files', 'writing files', 'reading and writing files'],
        'inputoutput.html#reading-and-writing-files', 'Processing stored records combines iteration with values held in collections.',
        'Read lines using a with block and write a filtered result to another file.'),
    'errors': concept('Handling exceptions', ['control'], ['exceptions', 'exception handling', 'error handling', 'handling errors'],
        'errors.html', 'Handling failed operations builds on branching between different outcomes.',
        'Catch a specific conversion error and explain why catching every exception can hide a bug.'),
    'modules': concept('Modules and imports', ['functions'], ['modules', 'module imports', 'import statements', 'packages'],
        'modules.html', 'Reusable functions give a concrete reason to split a program into modules.',
        'Move a function into a separate module and import it without running unrelated code.'),
    'classes': concept('Classes and objects', ['functions', 'collections'], ['classes', 'object oriented', 'object-oriented', 'class definition'],
        'classes.html', 'This route uses functions and collections before combining state and behaviour in objects.',
        'Define a class with one instance attribute and a method; create two independent instances.'),
}
GOALS = {
    'automation': {'label': 'Write a reliable file-processing script', 'targets': ['files', 'errors', 'functions'],
                   'task': 'Read records from a text file, filter them in a function, handle invalid input and save a summary.'},
    'organise': {'label': 'Organise a small Python program', 'targets': ['modules', 'classes', 'errors'],
                 'task': 'Split a small program into modules and use a class where it meaningfully groups state and behaviour.'},
    'foundations': {'label': 'Build a foundation in Python', 'targets': ['functions', 'collections'],
                    'task': 'Build a small program that uses values, decisions, loops, collections and a reusable function.'},
}


def validate_graph(graph):
    visiting, done = set(), set()
    def visit(key):
        if key not in graph: raise ValueError(f'Unknown prerequisite: {key}')
        if key in visiting: raise ValueError('Concept graph contains a cycle')
        if key in done: return
        visiting.add(key)
        for parent in graph[key]['requires']: visit(parent)
        visiting.remove(key); done.add(key)
    for key in graph: visit(key)


validate_graph(CONCEPTS)


def required_concepts(goal):
    if goal not in GOALS: raise ValueError('Choose a supported Python learning objective.')
    ordered = []
    def visit(key):
        for parent in CONCEPTS[key]['requires']: visit(parent)
        if key not in ordered: ordered.append(key)
    for key in GOALS[goal]['targets']: visit(key)
    return ordered


def catalogue_evidence(book):
    """Literal bounded term matches with source spans; intentionally conservative.

    Reject prerequisite/negation clauses rather than treating 'assumes knowledge
    of functions' as teaching functions. This is a heuristic, not semantic NLI.
    """
    text = ' '.join(str(book.get('abstract') or '').split())
    if not re.search(r'\bpython\b', str(book.get('title', ''))+' '+text, re.I): return {}
    evidence = {}
    for key, item in CONCEPTS.items():
        for sentence in re.split(r'(?<=[.!?;])\s+', text):
            if re.search(r'\b(assum\w*|prerequisite\w*|prior knowledge|already familiar|does not cover|not covered|excludes?|without covering)\b', sentence, re.I):
                continue
            for alias in item['aliases']:
                match = re.search(r'(?<!\w)'+re.escape(alias)+r'(?!\w)', sentence, re.I)
                if match:
                    # A short literal source span, not a generated summary.
                    start=max(0,match.start()-65); end=min(len(sentence),match.end()+85)
                    evidence[key]={'term':match.group(), 'excerpt':sentence[start:end], 'field':'abstract'}
                    break
            if key in evidence: break
    return evidence


def public_schema():
    return {'version':VERSION, 'domain':'Python',
            'concepts':[{'id':k, **v} for k,v in CONCEPTS.items()],
            'goals':[{'id':k, **v} for k,v in GOALS.items()],
            'notice':'The ordering is a project-authored study suggestion. Book descriptions indicate mentions, not verified coverage or mastery. The linked Python tutorial expects basic programming familiarity.'}


def reachable_mentions(mentions, remaining, planned):
    """Concept order within a suggested book; never invent an unmentioned bridge."""
    ready=[]; available=set(planned)
    for key in remaining:
        if key in mentions and set(CONCEPTS[key]['requires']) <= available:
            ready.append(key); available.add(key)
    return ready


def build_plan(books, scores, goal='automation', known=(), max_books=3, excluded=()):
    if set(known)-set(CONCEPTS): raise ValueError('Unrecognised known concept.')
    if max_books not in range(1,5): raise ValueError('Choose between one and four books.')
    if len(books)!=len(scores): raise ValueError('Book scores must align with the catalogue.')
    required=required_concepts(goal); known=set(known)
    remaining=[c for c in required if c not in known]
    initial=list(remaining); planned=set(known)
    excluded=set(excluded); used=set(); families=set(); steps=[]; book_supported=set()
    evidence=[catalogue_evidence(b) for b in books]
    while remaining:
        candidates=[]
        if len(used)<max_books:
            for i,b in enumerate(books):
                if i in used or str(b.get('isbn','')) in excluded or title_family(b.get('title','')) in families: continue
                if scores[i]<0.20 or len(str(b.get('abstract') or '').split())<20: continue
                gain=reachable_mentions(evidence[i],remaining,planned)
                if not gain: continue
                # Coverage-first greedy set cover with topical relevance as a tie-break influence.
                score=0.75*len(gain)/len(remaining)+0.25*float(scores[i])
                candidates.append((score,len(gain),str(b.get('isbn','')),i,gain))
        candidates.sort(key=lambda x:(-x[0],-x[1],x[2],x[3]))
        if candidates:
            score,_,_,i,gain=candidates[0]; b=books[i]
            alternative=candidates[1] if len(candidates)>1 else None
            steps.append({'kind':'book','title':b.get('title','Untitled'),'isbn':str(b.get('isbn','')),
                'url':b.get('book_url') or f"https://books.google.com/books?vid=ISBN{b.get('isbn','')}",
                'concepts':gain, 'evidence':{c:evidence[i][c] for c in gain},
                'reason':f'The description mentions {len(gain)} remaining concept(s) in a feasible suggested study order.',
                'score':round(score,4), 'semantic_similarity':round(float(scores[i]),4),
                'alternative':({'title':books[alternative[3]].get('title','Untitled'), 'score':round(alternative[0],4),
                    'concepts':alternative[4]} if alternative else None),
                'reading_note':'Focus on these concepts in the suggested order. The description does not verify chapter order, teaching depth or all prerequisites of this book.'})
            used.add(i); families.add(title_family(b.get('title',''))); book_supported.update(gain)
        else:
            key=next(c for c in remaining if set(CONCEPTS[c]['requires'])<=planned)
            gain=[key]
            steps.append({'kind':'bridge','title':CONCEPTS[key]['label'], 'url':CONCEPTS[key]['source_url'],
                'concepts':gain,'reason':('Book limit reached; use this reference for the remaining concept.' if len(used)>=max_books
                    else 'No eligible book description supports the next prerequisite step. This reference keeps the gap visible.'),
                'evidence':{}, 'reading_note':'Official Python reference; assumes basic programming familiarity. Ask for introductory support if the examples are unfamiliar.'})
        planned.update(gain); remaining=[c for c in remaining if c not in gain]
    return {'version':VERSION,'goal':goal,'goal_label':GOALS[goal]['label'],'practice_task':GOALS[goal]['task'],
        'known_concepts':[c for c in CONCEPTS if c in known], 'required_concepts':required,
        'remaining_concepts':initial,'skipped_concepts':[c for c in required if c in known],
        'steps':steps,'max_books':max_books,'books_used':len(used),
        'book_supported_concepts':[c for c in initial if c in book_supported],
        'bridge_concepts':[c for c in initial if c not in book_supported],
        'notice':public_schema()['notice'],
        'completion_note':'This is a proposed reading plan, not evidence that you have learned these concepts.'}


def compare_starting_point(books, scores, goal, known, max_books, excluded=()):
    plan=build_plan(books,scores,goal,known,max_books,excluded)
    fresh=build_plan(books,scores,goal,(),max_books,excluded)
    current_ids=[s['isbn'] for s in plan['steps'] if s['kind']=='book']
    fresh_ids=[s['isbn'] for s in fresh['steps'] if s['kind']=='book']
    plan['starting_point_comparison']={'without_known_concepts':len(fresh['remaining_concepts']),
        'with_known_concepts':len(plan['remaining_concepts']), 'skipped_concepts':plan['skipped_concepts'],
        'books_changed':current_ids!=fresh_ids,
        'fresh_book_titles':[s['title'] for s in fresh['steps'] if s['kind']=='book'],
        'note':'Only your declared knowledge changes in this comparison; it is not a prediction of time saved.'}
    return plan
