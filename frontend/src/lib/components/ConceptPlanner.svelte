<script lang="ts">
  import { onMount } from 'svelte';
  import BookIcon from './BookIcon.svelte';
  const API = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';
  type Concept = { id: string; label: string; requires: string[]; source_url: string; rationale: string; self_check: string };
  type Schema = { concepts: Concept[]; goals: { id: string; label: string; task: string }[]; notice: string };
  type Step = { kind: 'book' | 'bridge'; title: string; isbn?: string; url: string; concepts: string[]; reason: string; reading_note: string; evidence: Record<string, {term: string; excerpt: string}>; score?: number; alternative?: {title: string; score: number; concepts: string[]} | null };
  type Plan = { goal_label: string; practice_task: string; steps: Step[]; books_used: number; max_books: number; known_concepts: string[]; remaining_concepts: string[]; book_supported_concepts: string[]; bridge_concepts: string[]; notice: string; completion_note: string; starting_point_comparison: {without_known_concepts: number; with_known_concepts: number; skipped_concepts: string[]; books_changed: boolean; fresh_book_titles: string[]; note: string} };
  let schema: Schema | null = $state(null);
  let plan: Plan | null = $state(null);
  let goal = $state('automation');
  let known: string[] = $state([]);
  let maxBooks = $state(3);
  let excluded: string[] = $state([]);
  let loading = $state(false);
  let schemaLoading = $state(false);
  let error = $state('');
  let submitted = $state('');
  let dirty = $derived(!!plan && submitted !== JSON.stringify({goal, known: [...known].sort(), maxBooks}));
  const label = (id: string) => schema?.concepts.find(c => c.id === id)?.label ?? id;
  const info = (id: string) => schema?.concepts.find(c => c.id === id);
  async function loadSchema() {
    schemaLoading = true; error = '';
    try {
      const response = await fetch(`${API}/concept-map`);
      if (!response.ok) throw new Error('The Python planner is unavailable. Check that the backend is running.');
      schema = await response.json();
    } catch (e) { error = e instanceof Error ? e.message : 'Could not load the planner.'; }
    finally { schemaLoading = false; }
  }
  onMount(loadSchema);
  async function build(nextExcluded: string[] = excluded) {
    if (loading) return;
    loading = true; error = '';
    try {
      const response = await fetch(`${API}/concept-plan`, {method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({goal, known_concepts: known, max_books: Number(maxBooks), excluded_isbns: nextExcluded})});
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Could not build the plan. Check your selections.');
      plan = data; excluded = nextExcluded;
      submitted = JSON.stringify({goal, known: [...known].sort(), maxBooks});
    } catch (e) { error = e instanceof Error ? e.message : 'Could not build the plan.'; }
    finally { loading = false; }
  }
  function download() {
    if (!plan) return;
    const blob = new Blob([JSON.stringify({plan, concept_map: schema}, null, 2)], {type:'application/json'});
    const url = URL.createObjectURL(blob); const a = document.createElement('a');
    a.href = url; a.download = 'edugps-python-study-plan.json'; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
</script>

<section class="planner" aria-labelledby="planner-heading">
  <header><p class="eyebrow">Python study planner</p><h2 id="planner-heading">Start from what you know.</h2><p>Choose your goal and starting knowledge. Get a reading route with clear next steps.</p></header>
  {#if error}<p class="error" role="alert">{error}</p>{/if}
  {#if !schema}
    <button onclick={loadSchema} disabled={schemaLoading}>{schemaLoading ? 'Loading planner…' : 'Retry loading planner'}</button>
  {:else}
    <form onsubmit={(e) => {e.preventDefault(); build();}}>
      <div class="choices">
        <label>Your objective<select bind:value={goal} disabled={loading}>{#each schema.goals as g}<option value={g.id}>{g.label}</option>{/each}</select></label>
        <label>Maximum books<select bind:value={maxBooks} disabled={loading}>{#each [1,2,3,4] as n}<option value={n}>{n} {n === 1 ? 'book' : 'books'}</option>{/each}</select></label>
      </div>
      <fieldset disabled={loading}><legend>Concepts you already feel comfortable using</legend><p>Leave these unchecked if unsure. These are your own judgements, not a proficiency test.</p>
        <div class="checks">{#each schema.concepts as c}<label><input type="checkbox" bind:group={known} value={c.id}/>{c.label}</label>{/each}</div>
      </fieldset>
      <div class="actions"><button class="primary" type="submit" disabled={loading}>{loading ? 'Building your plan…' : 'Build my Python plan'}</button>
        {#if excluded.length}<button type="button" disabled={loading} onclick={() => build([])}>Restore avoided books ({excluded.length})</button>{/if}</div>
      {#if dirty}<p class="notice" role="status">Your choices have changed. Build the plan again to apply them; the plan below still uses your previous choices.</p>{/if}
    </form>
    {#if plan}
      <section class="result" aria-label="Python study plan" aria-busy={loading}>
        <div class="result-heading"><div><p class="eyebrow">Your proposed study plan</p><h3>{plan.goal_label}</h3></div><button onclick={download} disabled={loading || dirty}>Save plan</button></div>
        <p class="summary" role="status">{plan.books_used}/{plan.max_books} books · {plan.remaining_concepts.length} concepts to study{#if plan.bridge_concepts.length} · {plan.bridge_concepts.length} concepts use reference links{/if}</p>
        <details class="comparison"><summary>Your starting point · {plan.known_concepts.length} familiar concepts</summary><p>Starting knowledge: {plan.known_concepts.length ? plan.known_concepts.map(label).join(', ') : 'No concepts selected'}.</p>
          <p>Starting from scratch: {plan.starting_point_comparison.without_known_concepts} concepts to consider. With your selections: {plan.starting_point_comparison.with_known_concepts}.</p>
          <p>Skipped: {plan.starting_point_comparison.skipped_concepts.map(label).join(', ') || 'None'}.</p>
          <p>{plan.starting_point_comparison.books_changed ? 'The selected books change.' : 'The selected books stay the same; the concepts to focus on may change.'}</p>
          <p>Books suggested when starting from scratch: {plan.starting_point_comparison.fresh_book_titles.join('; ') || 'None'}.</p><small>{plan.starting_point_comparison.note}</small>
        </details>
        {#if !plan.steps.length}<p class="notice">You have marked every concept in this goal as familiar. Try the practice task below to check your confidence; no extra reading is prescribed.</p>{/if}
        <ol class="steps">{#each plan.steps as step, index}
          <li class:bridge={step.kind === 'bridge'}>
            <div class="step-head"><span class="resource-icon"><BookIcon /></span><div><p class="eyebrow">Step {index + 1} · {step.kind === 'book' ? 'Book' : 'Reference'}</p><h4>{step.title}</h4></div></div>
            
            <ol class="concepts">{#each step.concepts as id}<li><strong>{label(id)}</strong>
              <details><summary>Evidence &amp; practice</summary><p class="muted">Builds on: {info(id)?.requires.map(label).join(', ') || 'Starting concept'}.</p>
                {#if step.evidence[id]}<p>Catalogue term: <strong>{step.evidence[id].term}</strong></p><blockquote>{step.evidence[id].excerpt}</blockquote><p class="muted">An excerpt from the saved book description. A mention does not verify teaching depth.</p>{/if}
                <p>{info(id)?.rationale}</p><p><strong>Try it:</strong> {info(id)?.self_check}</p><a href={info(id)?.source_url} target="_blank" rel="noopener noreferrer">Python documentation for this concept ↗</a>
              </details></li>{/each}</ol>
            <details><summary>Why this resource?</summary><p>{step.reason}</p><p class="muted">{step.reading_note}</p></details>
            {#if step.alternative}<details><summary>Compare alternative</summary><p>The coverage-first score was {step.score}; the next eligible option, “{step.alternative.title}”, scored {step.alternative.score} and mentioned {step.alternative.concepts.map(label).join(', ')}. Equal scores use a stable identifier order. This is a selection rule, not a quality rating.</p></details>{/if}
            <div class="actions"><a href={step.url} target="_blank" rel="noopener noreferrer">{step.kind === 'book' ? 'View book' : 'Open reference'} ↗</a>{#if step.isbn}<button disabled={loading || dirty} onclick={() => build([...excluded, step.isbn!])}>Try another book</button>{/if}</div>
          </li>
        {/each}</ol>
        <section class="practice"><h4>Put the route to work</h4><p>{plan.practice_task}</p></section>
        <details><summary>About this plan</summary><p>{plan.completion_note}</p><p>{plan.notice}</p><p>A reference bridge marks missing book evidence or your book limit; it does not count as catalogue coverage. You may need additional guidance if you are new to programming.</p></details>
      </section>
    {/if}
  {/if}
</section>

<style>
  .planner {margin:24px 0;color: #000;font-family:Arial,sans-serif;line-height:1.6}
  header {max-width:720px;margin-bottom:28px} h2 {font:clamp(2rem,4vw,3rem) Georgia,serif;margin:6px 0} h3 {font-size:1.5rem;margin:0} h4 {font-size:1.12rem;margin:0} p {margin:8px 0 14px}
  .eyebrow {font-size:.7rem;text-transform:uppercase;letter-spacing:.12em;font-weight:bold;color: #000;margin:0}
  form {padding:24px;background:#faf6ef;border:1px solid #baa88d;border-radius:12px}.choices {display:flex;gap:24px;flex-wrap:wrap}.choices label {flex:1;min-width:200px;font-weight:bold} select {display:block;width:100%;margin-top:7px;padding:12px;border:1px solid #baa88d;border-radius:6px;background:white;color: #000;font:inherit}
  fieldset {margin:22px 0;border:0;padding:0} legend {font-weight:bold} fieldset p,.muted,small {font-size:.88rem;color: #000}.checks {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.checks label {display:flex;gap:10px;align-items:center;padding:8px;border:1px solid #baa88d;border-radius:6px}.checks input {width:18px;height:18px;accent-color: #9b8058}
  button {padding:10px 16px;border:1px solid #baa88d;border-radius:6px;background:#faf6ef;color: #000;cursor:pointer;font:inherit;font-size:.9rem}.primary {background:#d7c3a3;color: #000;font-weight:bold}button:disabled {opacity:.55;cursor:default}button:focus-visible,a:focus-visible,summary:focus-visible {outline:3px solid #baa88d;outline-offset:3px}.actions {display:flex;align-items:center;gap:16px;flex-wrap:wrap;margin-top:16px}a {color: #000;text-underline-offset:3px}
  .result {margin-top:35px}.result-heading {display:flex;align-items:center;justify-content:space-between;gap:16px}.summary {padding:12px 0;border-bottom:1px solid #baa88d}.comparison {margin:20px 0}.steps {list-style:none;padding:0;display:grid;gap:20px}.steps>li {background:#faf6ef;border:1px solid #baa88d;padding:24px;border-radius:12px}.steps>li.bridge {border-color:#baa88d;background:#faf6ef}.step-head {display:flex;gap:16px;align-items:start}.resource-icon {display:grid;place-items:center;flex-shrink:0;width:48px;height:56px;background:#faf6ef;border:1px solid #baa88d;border-radius:5px;color: #000}.concepts {padding-left:22px}.concepts>li {padding:10px 0;border-bottom:1px solid #baa88d}.concepts p {margin:5px 0}.practice {margin:28px 0}details {margin:12px 0}summary {cursor:pointer;font-weight:bold}blockquote {margin:10px 0;padding:8px 14px;border-left:2px solid #baa88d;color: #000}.notice {color: #000}.error {color: #000}
  @media(max-width:620px){.checks{grid-template-columns:1fr}form,.steps>li{padding:16px}.result-heading{align-items:start;flex-direction:column}}
</style>
