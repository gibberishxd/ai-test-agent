"""Deep mode (run 9): a second agent engine next to the current loop, built for finding as many
real, verified bugs as possible. A strong model drives a real browser with general tools
(screenshots, JavaScript, the page source, our checks), maps the app, writes a test plan from a
generic QA checklist, works through it, and reviews its own findings; every finding is then
verified in a fresh browser before it is shown."""
