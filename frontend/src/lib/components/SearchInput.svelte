<script lang="ts">
  let { value = $bindable<string>(), experience = $bindable('any'), goal = $bindable('balanced'), onSearch, disabled = false }: { value: string; experience?: string; goal?: string; onSearch: () => void; disabled?: boolean } = $props();
</script>

<form class="search" onsubmit={(event) => { event.preventDefault(); onSearch(); }}>
  <label class="topic">Learning topic
    <input type="search" bind:value {disabled} autocomplete="off" placeholder="Try ‘distributed systems’ or ‘modern JavaScript’" />
  </label>
  <div class="search-row">
    <label>Starting experience<select bind:value={experience} {disabled}><option value="any">No preference</option><option value="beginner">New to the subject</option><option value="experienced">Some prior knowledge</option></select></label>
    <label>Learning goal<select bind:value={goal} {disabled}><option value="balanced">Explore both</option><option value="theory">Understand the theory</option><option value="practice">Learn through practice</option></select></label>
    <button type="submit" {disabled}>Find books <span aria-hidden="true">→</span></button>
  </div>
  <p>Search saved books using your topic and preferences.</p>
</form>

<style>
  .search{box-sizing:border-box;width:100%;padding:18px;border:1px solid #cfc9bc;border-radius:14px;background:rgba(255,254,250,.88);box-shadow:0 12px 32px rgba(32,42,36,.08)}
  label{display:grid;gap:8px;color:#39463f;font-size:.85rem;min-width:0}.topic{font-weight:700}.search-row{display:grid;grid-template-columns:1fr 1fr auto;align-items:end;gap:16px;margin-top:16px}
  input,select{box-sizing:border-box;width:100%;min-width:0;padding:12px 14px;border:1px solid #aaa99f;border-radius:7px;color:#17201c;background:#fffefb;font:inherit;min-height:46px}input{font-size:1rem;font-weight:400}
  input:focus-visible,select:focus-visible,button:focus-visible{outline:3px solid #b38136;outline-offset:3px}
  button{min-height:46px;padding:12px 20px;border:1px solid #203f31;border-radius:7px;color:#fffdf8;background:#284f3c;font:inherit;font-weight:700;cursor:pointer}button:hover:not(:disabled){background:#1f3e2f}button span{margin-left:8px}button:disabled{opacity:.6;cursor:not-allowed}
  p{margin:12px 0 0;color:#687169;font-size:.78rem;line-height:1.5}
  @media(max-width:620px){.search-row{grid-template-columns:1fr}button{width:100%}}
</style>
