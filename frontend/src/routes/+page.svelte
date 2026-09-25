<script lang="ts">
  import SearchInput from '$lib/components/SearchInput.svelte';
  import BookIcon from '$lib/components/BookIcon.svelte';
  import ConceptPlanner from '$lib/components/ConceptPlanner.svelte';
  let mode = $state('discovery');
  let plannerOpened = $state(false);
  const API = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

  type Book = { title: string; author: string; isbn: string; book_url: string; score?: number; estimated_level?: string; content_orientation?: string; prerequisite_note?: string; profile_basis?: string };
  type RouteBook = { step: number; stage: string; title: string; author: string; isbn: string; published_date: string; thumbnail: string; book_url: string; rationale: string; stage_reason?: string; content_focus?: string; progression_reason?: string; explanation_basis?: string; estimated_level?: string; content_orientation?: string; prerequisite_note?: string; profile_basis?: string };

  let searchQuery = $state('');
  let submittedQuery = $state('');
  let recommendations: Book[] = $state([]);
  let excludedRecommendations: Book[] = $state([]);
  let selectedPath: string | null = $state(null);
  let isSearching = $state(false);
  let isLoadingRoadmap = $state(false);
  let searchError = $state('');
  let route: RouteBook[] = $state([]);
  let routeMethod = $state('');
  let selectedAnchorIsbn = $state('');
  let rejectedIsbns: string[] = $state([]);
  let replacingStep: number | null = $state(null);
  let routeOptions: Record<number, RouteBook[]> = $state({});
  let routeOptionIndex: Record<number, number> = $state({});
  let cycleComplete: Record<number, boolean> = $state({});
  let cycleNotices: Record<number, string> = $state({});
  let feedbackVotes: Record<string, number> = $state({});
  let feedbackPending: string | null = $state(null);
  let feedbackNotices: Record<string, string> = $state({});
  let catalogueSize = $state(0);
  let topicCoverage = $state(0);
  let addedBooks = $state(0);
  let isRefreshing = $state(false);
  let refreshNotice = $state('');
  let evidenceNotice = $state('');
  let experience = $state('any');
  let goal = $state('balanced');
  let submittedExperience = $state('any');
  let submittedGoal = $state('balanced');
  let missingStages: {stage: string; reason: string}[] = $state([]);
  const busy = $derived(isSearching || isRefreshing || isLoadingRoadmap || replacingStep !== null || feedbackPending !== null);
  function preferenceParams(level = submittedExperience, purpose = submittedGoal) {
    return `&experience=${encodeURIComponent(level)}&goal=${encodeURIComponent(purpose)}`;
  }

  async function refreshCatalogue() {
    const query = searchQuery.trim();
    if (!query || busy) return;
    isRefreshing = true;
    refreshNotice = '';
    try {
      const response = await fetch(`${API}/refresh-data?query=${encodeURIComponent(query)}`, { method: 'POST' });
      if (!response.ok) throw new Error(await getApiError(response));
      const data = await response.json();
      addedBooks = data.added_count ?? 0;
      refreshNotice = `Added ${addedBooks} books for “${query}”. Search again to see the updated catalogue.`;
    } catch {
      refreshNotice = 'Refresh unavailable. Your existing results and saved catalogue are still available. Try again later.';
    } finally { isRefreshing = false; }
  }

  async function getApiError(response: Response) {
    const data = await response.json().catch(() => null);
    return data?.detail ?? `Request failed (${response.status}).`;
  }

  async function handleSearch() {
    const query = searchQuery.trim();
    if (!query || busy) return;
    isSearching = true;
    searchError = '';
    evidenceNotice = '';
    refreshNotice = '';
    recommendations = [];
    excludedRecommendations = [];
    selectedPath = null;
    try {
      const searchResponse = await fetch(`${API}/search?query=${encodeURIComponent(query)}${preferenceParams(experience, goal)}`);
      if (!searchResponse.ok) throw new Error(await getApiError(searchResponse));
      const searchData = await searchResponse.json();
      recommendations = searchData.recommendations ?? [];
      excludedRecommendations = searchData.excluded_recommendations ?? [];
      catalogueSize = searchData.catalogue_size ?? 0;
      topicCoverage = searchData.topic_coverage ?? 0;
      evidenceNotice = searchData.evidence_notice ?? '';
      submittedQuery = query;
      submittedExperience = experience;
      submittedGoal = goal;
      const feedbackResponse = await fetch(`${API}/feedback?query=${encodeURIComponent(query)}`);
      feedbackVotes = feedbackResponse.ok ? ((await feedbackResponse.json()).votes ?? {}) : {};
      feedbackNotices = {};
    } catch (error) {
      searchError = error instanceof Error ? error.message : 'Search failed. Please try again.';
    } finally { isSearching = false; }
  }

  async function submitFeedback(book: Book, selectedVote: 1 | -1 | 0) {
    if (busy) return;
    const vote = selectedVote !== 0 && feedbackVotes[book.isbn] === selectedVote ? 0 : selectedVote;
    feedbackPending = book.isbn;
    searchError = '';
    try {
      const response = await fetch(`${API}/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: submittedQuery, isbn: book.isbn, vote })
      });
      if (!response.ok) throw new Error(await getApiError(response));
      const nextVotes = { ...feedbackVotes };
      if (vote === 0) delete nextVotes[book.isbn];
      else nextVotes[book.isbn] = vote;
      feedbackVotes = nextVotes;
      feedbackNotices = { ...feedbackNotices, [book.isbn]: vote === 0 ? 'Preference cleared' : vote === 1 ? 'Marked useful' : 'Marked not useful' };
      if (vote === -1) {
        // A cached route or replacement history must not restore a rejected book.
        selectedPath = null;
        route = [];
        routeOptions = {};
        recommendations = recommendations.filter((candidate) => candidate.isbn !== book.isbn);
        if (!excludedRecommendations.some((candidate) => candidate.isbn === book.isbn)) {
          excludedRecommendations = [book, ...excludedRecommendations];
        }
      } else if (vote === 0) {
        const searchResponse = await fetch(`${API}/search?query=${encodeURIComponent(submittedQuery)}${preferenceParams()}`);
        if (!searchResponse.ok) throw new Error(await getApiError(searchResponse));
        const searchData = await searchResponse.json();
        recommendations = searchData.recommendations ?? [];
        excludedRecommendations = searchData.excluded_recommendations ?? [];
      }
    } catch (error) {
      searchError = error instanceof Error ? error.message : 'Could not save your preference.';
    } finally {
      feedbackPending = null;
    }
  }

  async function handleSelectRecommendation(book: Book) {
    if (busy) return;
    isLoadingRoadmap = true;
    searchError = '';
    try {
      const response = await fetch(`${API}/roadmap?isbn=${encodeURIComponent(book.isbn)}&query=${encodeURIComponent(submittedQuery)}${preferenceParams()}`);
      if (!response.ok) throw new Error(await getApiError(response));
      const roadmap = await response.json();
      selectedPath = roadmap.title;
      selectedAnchorIsbn = book.isbn;
      route = roadmap.route ?? [];
      missingStages = roadmap.missing_stages ?? [];
      routeMethod = roadmap.method ?? '';
      rejectedIsbns = [];
      routeOptions = Object.fromEntries(route.map((item) => [item.step, [item]]));
      routeOptionIndex = Object.fromEntries(route.map((item) => [item.step, 0]));
      cycleComplete = {};
      cycleNotices = {};
    } catch (error) {
      searchError = error instanceof Error ? error.message : 'Could not build the roadmap.';
    } finally { isLoadingRoadmap = false; }
  }

  async function replaceBook(item: RouteBook) {
    if (busy) return;
    const options = routeOptions[item.step] ?? [item];
    const currentIndex = routeOptionIndex[item.step] ?? 0;

    if (currentIndex < options.length - 1) {
      showRouteOption(item.step, currentIndex + 1);
      return;
    }
    if (options.length >= 4 || cycleComplete[item.step]) {
      showRouteOption(item.step, 0);
      return;
    }
    replacingStep = item.step;
    searchError = '';
    try {
      const response = await fetch(`${API}/roadmap/replace`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          anchor_isbn: selectedAnchorIsbn,
          query: submittedQuery,
          stage: item.stage,
          experience: submittedExperience,
          goal: submittedGoal,
          used_isbns: route.map((book) => book.isbn),
          rejected_isbns: rejectedIsbns
        })
      });
      if (!response.ok) throw new Error(await getApiError(response));
      const replacement = await response.json();
      if (replacement.exhausted) {
        cycleComplete = { ...cycleComplete, [item.step]: true };
        cycleNotices = { ...cycleNotices, [item.step]: replacement.message };
        return;
      }
      rejectedIsbns = [...rejectedIsbns, item.isbn];
      const updatedOptions = [...options, { ...replacement, step: item.step }];
      routeOptions = { ...routeOptions, [item.step]: updatedOptions };
      routeOptionIndex = { ...routeOptionIndex, [item.step]: updatedOptions.length - 1 };
      route = route.map((book) => book.step === item.step ? updatedOptions.at(-1)! : book);
    } catch (error) {
      searchError = error instanceof Error ? error.message : 'Could not replace this book.';
    } finally { replacingStep = null; }
  }

  function showRouteOption(step: number, index: number) {
    const option = routeOptions[step]?.[index];
    if (!option) return;
    routeOptionIndex = { ...routeOptionIndex, [step]: index };
    route = route.map((book) => book.step === step ? option : book);
    searchError = '';
  }

  function previousBook(item: RouteBook) {
    const options = routeOptions[item.step] ?? [item];
    const currentIndex = routeOptionIndex[item.step] ?? 0;
    showRouteOption(item.step, (currentIndex - 1 + options.length) % options.length);
  }

</script>

<svelte:head><title>EduGPS — Map your learning route</title><meta name="description" content="Turn a subject into a clear, book-based learning route." /></svelte:head>

<main>
  <nav aria-label="Primary navigation">
    <a class="brand" href="/" aria-label="EduGPS home"><span>EG</span> EduGPS</a>
    <p>Independent learning, mapped clearly.</p>
    <span class="prototype-label">Research prototype</span>
  </nav>

  <section class="hero">
    <div><p class="eyebrow">A clearer way into any subject</p><h1>Spend less time searching.<br />Start learning sooner.</h1><p class="lede">Tell us what you want to understand. EduGPS finds relevant books and turns them into a practical route you can explore at your own pace.</p></div>
    <aside class="method-note"><span>How it works</span><ol><li><b>01</b> Name a subject</li><li><b>02</b> Review the reading list</li><li><b>03</b> Follow your route</li></ol></aside>
  </section>

  <div class="mode-switch" role="group" aria-label="Choose a planning mode">
    <button type="button" aria-pressed={mode === 'discovery'} onclick={() => mode = 'discovery'}>Explore any topic</button>
    <button type="button" aria-pressed={mode === 'python'} onclick={() => { plannerOpened = true; mode = 'python'; }}>Plan Python around what I know</button>
  </div>
  {#if plannerOpened}<div class="planner-workspace" hidden={mode !== 'python'}><ConceptPlanner /></div>{/if}
  <section class="workspace" aria-label="Learning path search" hidden={mode !== 'discovery'}>
    <SearchInput bind:value={searchQuery} bind:experience bind:goal onSearch={handleSearch} disabled={busy}/>
    <div class="learner-controls">
      <button type="button" onclick={refreshCatalogue} disabled={busy || !searchQuery.trim()}>{isRefreshing ? 'Refreshing…' : 'Find more books online'}</button>
      <span class="search-context">Need more options? Refresh the catalogue for this topic.</span>
    </div>
    {#if refreshNotice}<p role="status">{refreshNotice}</p>{/if}
    {#if evidenceNotice}<p class="search-context" role="status">{evidenceNotice}</p>{/if}

    {#if isSearching}<div class="status" aria-live="polite"><span></span>Checking the shelves and ranking useful matches…</div>
    {:else if searchError}<p class="error" role="alert">{searchError}</p>{/if}

    {#if recommendations.length > 0}
      <div class="results-container">
        <p class="catalogue-coverage">Saved catalogue · {topicCoverage} books collected for this topic · {catalogueSize} saved overall</p>
        <div class="section-heading"><div><p class="eyebrow">Reading shortlist</p><h2>Matches for “{submittedQuery}”</h2></div><span>{recommendations.length} books</span></div>
        <div class="results-grid">
          {#each recommendations as book, index}
            <article class="book-card">
              <div class="book-number">{String(index + 1).padStart(2, '0')}</div>
              <div class="book-identity"><span class="book-symbol"><BookIcon /></span><p class="match">Reading suggestion</p></div>
              <h3>{book.title}</h3><p class="author">{book.author}</p>
              {#if book.estimated_level || book.content_orientation}<div class="profile-badges" aria-label="Estimated book profile">{#if book.estimated_level}<span>Estimated: {book.estimated_level}</span>{/if}{#if book.content_orientation}<span>Style: {book.content_orientation}</span>{/if}</div>{/if}
              <details class="book-metadata"><summary>Book details</summary><p class="isbn">ISBN {book.isbn}</p><p>Suggested using the saved book description.</p></details>
              <div class="preference-row" aria-label={`Rate ${book.title}`}>
                <span>Was this useful?</span>
                <button class:active={feedbackVotes[book.isbn] === 1} type="button" aria-label="Mark useful" aria-pressed={feedbackVotes[book.isbn] === 1} onclick={() => submitFeedback(book, 1)} disabled={feedbackPending !== null}>Useful</button>
                <button class:active={feedbackVotes[book.isbn] === -1} type="button" aria-label="Mark not useful" aria-pressed={feedbackVotes[book.isbn] === -1} onclick={() => submitFeedback(book, -1)} disabled={feedbackPending !== null}>Not useful</button>
              </div>
              {#if feedbackNotices[book.isbn]}<p class="feedback-notice" aria-live="polite">{feedbackNotices[book.isbn]}</p>{/if}
              <div class="book-actions"><button type="button" disabled={busy} onclick={() => handleSelectRecommendation(book)}>Build roadmap</button><a href={book.book_url} target="_blank" rel="noopener noreferrer">View book ↗</a></div>
            </article>
          {/each}
        </div>
      </div>
    {/if}

    {#if excludedRecommendations.length > 0}
      <details class="excluded-books">
        <summary>Hidden as not useful ({excludedRecommendations.length})</summary>
        <div>
          {#each excludedRecommendations as book}
            <span>{book.title}</span>
            <button type="button" onclick={() => submitFeedback(book, 0)} disabled={feedbackPending !== null}>Undo</button>
          {/each}
        </div>
      </details>
    {/if}

    {#if selectedPath && route.length > 0}
      <div class="route-container">
        <div class="route-heading"><div><p class="eyebrow">Continue after your starting book</p><h2>Your route from “{selectedPath}”</h2></div><p>{routeMethod}</p></div>
        {#if missingStages.length > 0}<aside class="route-gaps" aria-label="Unfilled learning stages"><h3>This route has gaps</h3><p>We have left stages unfilled where the catalogue lacks sufficient evidence. Listed books are suggestions, not verified prerequisites.</p>{#each missingStages as gap}<p><strong>{gap.stage}:</strong> {gap.reason}</p>{/each}</aside>{/if}
        <ol class="reading-route">
          {#each route as item}
            <li class="route-card">
              <div class="route-index"><span>{String(item.step).padStart(2, '0')}</span><i></i></div>
              {#if item.thumbnail}<img src={item.thumbnail} alt="" />{:else}<div class="cover-placeholder" aria-hidden="true">{item.step}</div>{/if}
              <div class="route-copy">
                <p class="stage">{item.stage}</p>
                <h3>{item.title}</h3>
                <p class="book-meta">{item.author}{item.published_date ? ` · ${item.published_date.slice(0, 4)}` : ''}</p>
                {#if item.estimated_level || item.content_orientation}<div class="profile-badges" aria-label="Estimated book profile">{#if item.estimated_level}<span>Estimated: {item.estimated_level}</span>{/if}{#if item.content_orientation}<span>Style: {item.content_orientation}</span>{/if}</div>{/if}
                <p class="rationale">{item.rationale}</p>
                {#if item.stage_reason || item.content_focus || item.progression_reason}
                  <details class="book-reasoning">
                    <summary>Why this book?</summary>
                    <div class="reasoning-details">
                      {#if item.stage_reason}<p><b>Why this stage</b><span>{item.stage_reason}</span></p>{/if}
                      {#if item.content_focus}<p><b>What you’ll find</b><span>{item.content_focus}</span></p>{/if}
                      {#if item.progression_reason}<p><b>Why it follows</b><span>{item.progression_reason}</span></p>{/if}
                      {#if item.prerequisite_note}<p><b>Prerequisites</b><span>{item.prerequisite_note}</span></p>{/if}
                      {#if item.explanation_basis}<small>{item.explanation_basis}</small>{/if}
                      {#if item.profile_basis}<small>{item.profile_basis}</small>{/if}
                    </div>
                  </details>
                {/if}
              </div>
              <div class="route-action"><a href={item.book_url} target="_blank" rel="noopener noreferrer">View book <span>↗</span></a>{#if item.stage === 'Foundation'}<span class="fixed-stage">Fixed starting point</span>{:else}<div class="cycle-controls"><button type="button" aria-label={`Return to the previous ${item.stage} book`} title="Previous book" onclick={() => previousBook(item)} disabled={(routeOptions[item.step]?.length ?? 1) < 2 || replacingStep !== null}>←</button><span>Option {(routeOptionIndex[item.step] ?? 0) + 1}{#if cycleComplete[item.step]} of {routeOptions[item.step]?.length ?? 1}{:else} (up to 4){/if}</span><button class="try-another" type="button" aria-label={`Try another book for ${item.stage}`} onclick={() => replaceBook(item)} disabled={replacingStep !== null || (cycleComplete[item.step] && (routeOptions[item.step]?.length ?? 1) < 2)}>{replacingStep === item.step ? 'Finding…' : 'Try another book →'}</button></div><small class="cycle-hint">{cycleNotices[item.step] ?? 'You can return to an earlier option with the back arrow.'}</small>{/if}<small>ISBN {item.isbn}</small></div>
            </li>
          {/each}
        </ol>
      </div>
    {:else if isLoadingRoadmap}<div class="status" aria-live="polite"><span></span>Arranging your reading route…</div>{/if}
  </section>

  <footer><span>EduGPS</span><p>Built as a final-year research prototype for self-directed learners.</p></footer>
</main>

<style>
  .mode-switch{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:20px}.mode-switch button{min-height:44px;padding:11px 16px;border:1px solid #baa88d;border-radius:6px;background:#faf6ef;color: #000;font:inherit;font-size:.9rem;cursor:pointer}.mode-switch button[aria-pressed="true"]{background:#d7c3a3;border-color:#baa88d;color: #000}.mode-switch button:hover{border-color:#baa88d}.mode-switch button:focus-visible{outline:3px solid #baa88d;outline-offset:3px}
  .learner-controls{display:flex;flex-wrap:wrap;align-items:end;gap:16px;margin-top:18px}.learner-controls button{padding:10px;border:1px solid #baa88d;border-radius:6px;background:#faf6ef;color: #000}.learner-controls button{cursor:pointer}.search-context{color: #000;font-size:.85rem;line-height:1.5}.route-gaps{padding:18px;border:1px solid #baa88d;background:#faf6ef;border-radius:8px;margin-bottom:20px}.route-gaps h3{margin-top:0}button:disabled{opacity:.6;cursor:not-allowed}.catalogue-coverage{max-width:100%;box-sizing:border-box;white-space:normal}
  nav,.hero,.mode-switch,.planner-workspace,.workspace,footer{width:min(1160px,calc(100% - 48px));margin-inline:auto}nav{height:78px;display:flex;align-items:center;gap:24px;border-bottom:1px solid #baa88d}nav p{margin:0;color: #000;font-size:.82rem}.brand{display:flex;align-items:center;gap:10px;color: #000;font-family:Georgia,serif;font-size:1.15rem;font-weight:700;text-decoration:none}.brand span{display:grid;width:34px;height:34px;place-items:center;border-radius:50%;color: #000;background:#d7c3a3;font-family:Inter,sans-serif;font-size:.65rem}.prototype-label{margin-left:auto;padding:6px 9px;border:1px solid #baa88d;border-radius:4px;color: #000;font-size:.66rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase}
  .hero{display:grid;grid-template-columns:minmax(0,1.7fr) minmax(250px,.65fr);gap:80px;padding:76px 0 54px}.eyebrow{margin:0 0 12px;color: #000;font-size:.69rem;font-weight:800;letter-spacing:.14em;text-transform:uppercase}h1,h2,h3{font-family:Georgia,"Times New Roman",serif}h1{max-width:820px;margin:0;font-size:clamp(2.7rem,6vw,5.25rem);font-weight:500;letter-spacing:-.045em;line-height:.98}.lede{max-width:680px;margin:25px 0 0;color: #000;font-size:1.05rem;line-height:1.7}.method-note{align-self:end;padding:20px 0 4px;border-top:2px solid #baa88d}.method-note>span{color: #000;font-size:.7rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase}.method-note ol{margin:16px 0 0;padding:0;list-style:none}.method-note li{display:flex;gap:14px;padding:10px 0;border-top:1px solid #baa88d;color: #000;font-size:.84rem}.method-note b{color: #000;font-size:.7rem}
  .workspace,.planner-workspace{padding-bottom:80px}.status,.error{margin:20px 2px}.status{display:flex;align-items:center;gap:10px;color: #000;font-size:.86rem}.status span{width:10px;height:10px;border:2px solid #baa88d;border-top-color:#baa88d;border-radius:50%;animation:spin 800ms linear infinite}@keyframes spin{to{transform:rotate(360deg)}}.error{color: #000}.results-container{margin-top:54px}.section-heading,.route-heading{display:flex;align-items:end;justify-content:space-between;gap:24px;margin-bottom:20px}.section-heading h2,.route-heading h2{margin:0;font-size:clamp(1.65rem,3vw,2.4rem);font-weight:500;letter-spacing:-.025em}.section-heading>span{color: #000;font-size:.78rem}.route-heading>p{max-width:360px;margin:0;color: #000;font-size:.78rem;line-height:1.55;text-align:right}
  .results-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(235px,1fr));gap:14px}.book-card{position:relative;min-height:300px;padding:22px;border:1px solid #baa88d;border-radius:10px;background:#faf6ef;box-shadow:0 6px 18px rgba(110,85,50,.045);transition:transform 170ms,box-shadow 170ms}.book-card:hover{transform:translateY(-3px);box-shadow:0 14px 30px rgba(110,85,50,.09)}.book-number{position:absolute;top:20px;right:20px;color: #000;font-family:Georgia,serif;font-size:1.1rem}.match{margin:0 40px 46px 0;color: #000;font-size:.67rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase}.book-card h3{margin:0 0 12px;font-size:1.35rem;font-weight:500;line-height:1.25}.author{margin:0;color: #000;font-size:.86rem}.isbn{margin:9px 0 24px;color: #000;font-size:.7rem}.book-actions{position:absolute;right:22px;bottom:22px;left:22px;display:flex;gap:12px;align-items:center}.book-actions button{padding:9px 12px;border:1px solid #baa88d;border-radius:6px;color: #000;background:#d7c3a3;font-size:.76rem;font-weight:700;cursor:pointer}.book-actions a{color: #000;font-size:.76rem;font-weight:700;text-decoration:none}.book-actions a:hover{text-decoration:underline}
  .route-container{margin-top:68px;padding-top:44px;border-top:1px solid #baa88d}.reading-route{margin:0;padding:0;list-style:none;border-top:1px solid #baa88d}.route-card{display:grid;grid-template-columns:62px 68px minmax(0,1fr) auto;gap:24px;align-items:center;min-height:160px;padding:22px 8px;border-bottom:1px solid #baa88d;transition:background 160ms}.route-card:hover{background:rgba(250,246,239,.55)}.route-index{align-self:stretch;display:flex;flex-direction:column;align-items:center;color: #000;font-family:Georgia,serif;font-size:1rem}.route-index i{width:1px;flex:1;margin-top:12px;background:#e6d7bf}.route-card:last-child .route-index i{display:none}.route-card img,.cover-placeholder{width:68px;height:100px;border-radius:3px;object-fit:cover;box-shadow:0 5px 12px rgba(110,85,50,.16)}.cover-placeholder{display:grid;place-items:center;color: #000;background:#d7c3a3;font-family:Georgia,serif;font-size:1.4rem}.stage{margin:0 0 7px;color: #000;font-size:.66rem;font-weight:800;letter-spacing:.12em;text-transform:uppercase}.route-copy h3{margin:0 0 7px;font-size:1.35rem;font-weight:500}.book-meta{margin:0;color: #000;font-size:.8rem}.rationale{max-width:650px;margin:12px 0 0;color: #000;font-size:.84rem;line-height:1.55}.route-action{display:flex;min-width:245px;align-items:flex-end;flex-direction:column;gap:8px}.route-action>a{padding:10px 13px;border:1px solid #baa88d;border-radius:6px;color: #000;font-size:.75rem;font-weight:750;text-decoration:none}.route-action>a:hover{color: #000;background:#d7c3a3}.cycle-controls{display:flex;align-items:center;overflow:hidden;border:1px solid #baa88d;border-radius:7px;background:#faf6ef;box-shadow:0 2px 7px rgba(110,85,50,.08)}.cycle-controls button{display:grid;width:34px;height:34px;place-items:center;padding:0;border:0;color: #000;background:transparent;font-size:.8rem;cursor:pointer}.cycle-controls button:hover:not(:disabled){background:#faf6ef}.cycle-controls button:disabled{color: #000;cursor:not-allowed}.cycle-controls span{padding:0 9px;border-right:1px solid #baa88d;border-left:1px solid #baa88d;color: #000;font-size:.65rem;font-weight:750;white-space:nowrap}.cycle-controls .try-another{width:auto;padding:0 13px;color: #000;background:#d7c3a3;font-size:.7rem;font-weight:750;white-space:nowrap}.cycle-controls .try-another:hover:not(:disabled){background:#d7c3a3}.cycle-controls .try-another:disabled{color: #000;background:#d7c3a3}.fixed-stage{color: #000;font-size:.68rem;font-style:italic}.route-action small{color: #000;font-size:.62rem}.route-action .cycle-hint{max-width:245px;color: #000;text-align:right}
  footer{display:flex;justify-content:space-between;gap:24px;padding:25px 0 38px;border-top:1px solid #baa88d;color: #000;font-size:.75rem}footer span{color: #000;font-family:Georgia,serif;font-weight:700}footer p{margin:0}@media(max-width:760px){nav,.hero,.mode-switch,.planner-workspace,.workspace,footer{width:min(100% - 28px,1160px)}nav p{display:none}.hero{grid-template-columns:1fr;gap:38px;padding-top:52px}.method-note{max-width:420px}.section-heading,.route-heading{align-items:start;flex-direction:column}.route-heading>p{text-align:left}.route-card{grid-template-columns:36px 58px minmax(0,1fr);gap:14px}.route-card img,.cover-placeholder{width:58px;height:86px}.route-action{grid-column:3;align-items:flex-start}footer{flex-direction:column}}@media(prefers-reduced-motion:reduce){.book-card{transition:none}}
  .book-card{min-height:0;display:flex;flex-direction:column}.book-identity{display:flex;align-items:center;gap:12px;margin:0 30px 20px 0}.book-symbol{display:grid;place-items:center;flex-shrink:0;width:48px;height:56px;background:#faf6ef;border:1px solid #baa88d;border-radius:5px;color: #000}.book-identity .match{margin:0}.book-metadata{font-size:.75rem;color: #000;margin:12px 0}.book-metadata summary{cursor:pointer}.book-metadata .isbn{margin:8px 0}.book-actions{position:static;margin-top:auto;padding-top:20px;flex-wrap:wrap}.preference-row{display:flex;align-items:center;gap:5px;margin-bottom:5px}.preference-row span{margin-right:3px;color: #000;font-size:.65rem}.preference-row button{padding:5px 7px;border:1px solid #baa88d;border-radius:5px;color: #000;background:#faf6ef;font-size:.63rem;cursor:pointer}.preference-row button:hover:not(:disabled),.preference-row button.active{border-color:#baa88d;color: #000;background:#d7c3a3}.preference-row button:disabled{cursor:not-allowed;opacity:.65}.feedback-notice{margin:3px 0 0;color: #000;font-size:.63rem}
  .excluded-books{margin-top:18px;padding:12px 15px;border:1px solid #baa88d;border-radius:8px;color: #000;background:#faf6ef;font-size:.75rem}.excluded-books summary{cursor:pointer;font-weight:750}.excluded-books>div{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:9px 16px;align-items:center;margin-top:12px}.excluded-books button{padding:5px 9px;border:1px solid #baa88d;border-radius:5px;color: #000;background:#faf6ef;font-size:.68rem;cursor:pointer}.excluded-books button:hover:not(:disabled){color: #000;background:#d7c3a3}
  .book-reasoning{max-width:680px;margin-top:12px;border-top:1px solid #baa88d}.book-reasoning summary{width:max-content;padding:9px 0 3px;color: #000;font-size:.72rem;font-weight:800;cursor:pointer}.book-reasoning summary:hover{text-decoration:underline}.reasoning-details{display:grid;gap:9px;margin-top:7px;padding:12px 14px;border-left:3px solid #baa88d;border-radius:0 6px 6px 0;background:#faf6ef}.reasoning-details p{display:grid;grid-template-columns:112px minmax(0,1fr);gap:10px;margin:0;color: #000;font-size:.76rem;line-height:1.5}.reasoning-details b{color: #000;font-size:.68rem;letter-spacing:.02em;text-transform:uppercase}.reasoning-details span{min-width:0}.reasoning-details small{color: #000;font-size:.64rem;font-style:italic}
  .profile-badges{display:flex;flex-wrap:wrap;gap:5px;margin:8px 0 2px}.profile-badges span{padding:4px 7px;border:1px solid #baa88d;border-radius:999px;color: #000;background:#faf6ef;font-size:.62rem;font-weight:750}
  .catalogue-coverage{width:max-content;margin:0 0 14px auto;padding:6px 9px;border:1px solid #baa88d;border-radius:999px;color: #000;background:#faf6ef;font-size:.68rem}
  @media(max-width:760px){.reasoning-details p{grid-template-columns:1fr;gap:2px}.book-reasoning summary{padding-top:11px}}
</style>
