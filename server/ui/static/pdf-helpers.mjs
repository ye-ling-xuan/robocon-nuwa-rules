/** PyMuPDF top-left page points -> PDF.js viewport pixels, including rotation. */
export function topLeftRectToViewport(rect, view, viewport) {
  const [x0, y0, x1, y1] = rect;
  const box = viewport.convertToViewportRectangle([view[0]+x0, view[3]-y0, view[0]+x1, view[3]-y1]);
  return [Math.min(box[0],box[2]), Math.min(box[1],box[3]), Math.max(box[0],box[2]), Math.max(box[1],box[3])];
}

/** Find a continuous quote across PDF.js text spans without interpreting HTML. */
export function quoteRanges(container, quote) {
  const clean = value => value.normalize("NFKC").replace(/\s/g, "").toLowerCase();
  const needle = clean(quote || "");
  if (!container || !needle) return [];
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
  let node, haystack = ""; const positions = [];
  while ((node = walker.nextNode())) {
    let offset = 0;
    for (const character of node.textContent) {
      const normalized = clean(character);
      for (let i=0; i<normalized.length; i++) positions.push({node, start: offset, end: offset+character.length});
      haystack += normalized; offset += character.length;
    }
  }
  const start = haystack.indexOf(needle);
  if (start < 0) return [];
  const matched = positions.slice(start, start+needle.length), groups = [];
  for (const position of matched) {
    const previous = groups.at(-1);
    if (previous?.node === position.node) previous.end = position.end;
    else groups.push({...position});
  }
  return groups.map(group => {
    const range = document.createRange(); range.setStart(group.node, group.start); range.setEnd(group.node, group.end); return range;
  });
}
