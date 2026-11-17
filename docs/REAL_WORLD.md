# Real-world benchmark (run 8, N4)

Every earlier number comes from two demo apps we wrote ourselves, with bugs we planted. This
benchmark asks a different question: **does the agent find real bugs that real users reported in
real open-source web apps?** Each bug below was reported in the app's public issue tracker and
fixed in an identifiable commit. We run the app at the commit just before the fix, on this Mac
only, and point the agent at it.

> This file holds the answer key (issue links, the reporters' words, fix commits). Like the demo
> apps' `bugs.json`, it lives in the repo, which claude-cli can never read (it runs in a temp
> folder outside the repo; `outside_repo` is checked before every call).

## How the apps were picked

Criteria (the owner's): a license that allows local use; starts locally with npm or Docker with no
paid service or external account; a UI the agent can reach without complex setup; at least three
user-visible **functional** UI bugs in the public tracker, each fixed in an identifiable commit.
No security bugs, no purely visual bugs. Small, well-known apps that start fast were preferred.

Considered and not picked: Excalidraw and tldraw (canvas apps: the agent acts on DOM elements, not
on a drawing surface); Uptime Kuma (the app itself would contact public hosts); Linkding (adding a
bookmark fetches the bookmarked public page); Memos, Gitea, Vikunja (Go builds per commit: slow,
and their Docker images are per release, not per commit); Actual Budget (large install); TiddlyWiki
(kept as a reserve: zero install, but its tracker's fixes are harder to tie to single commits).

### 1. IT-Tools (`CorentinTh/it-tools`, GPL-3.0, ~41k stars)
A collection of ~80 small developer tools (converters, generators, formatters) in Vue 3 + Vite.
Everything runs in the browser: no backend, no account, no data to seed. `pnpm install && pnpm dev`
starts it in seconds. Its tracker has many functional bugs with "fix(tool): ..." commits that close
them. The bugs need judgement (a wrong conversion, an input that can't be edited, a panel that
vanishes), the kind the agent's AI-only recall measures.

| Bug | Issue (reporter's words, shortened) | Fixed by | Start page |
|---|---|---|---|
| IT-1 | [#274](https://github.com/CorentinTh/it-tools/issues/274) Roman numeral converter: "Add 'IVX' to 'Roman to Arabic' … You will see '4'. IVX is not valid roman numerical" | [8930e139](https://github.com/CorentinTh/it-tools/commit/8930e139b28f) (PR #332, 2023-04-08) | `/roman-numeral-converter` |
| IT-2 | [#402](https://github.com/CorentinTh/it-tools/issues/402) IPv4 address converter: "Try to edit IPv4" (the input can't be changed) | [7aed9c56](https://github.com/CorentinTh/it-tools/commit/7aed9c56fd06) (PR #403, 2023-05-15) | `/ipv4-address-converter` |
| IT-3 | [#652](https://github.com/CorentinTh/it-tools/issues/652) Encrypt / decrypt text: "Select RC4 as Encryption algorithm in the Decrypt container … you can make the whole container disappear" | [02b0d0d1](https://github.com/CorentinTh/it-tools/commit/02b0d0d1a13c) (PR #711, 2023-11-01) | `/encryption` |
| IT-4 | [#1365](https://github.com/CorentinTh/it-tools/issues/1365) "When on a tool, the favorite button is not working … it is not adding to favorite (on a tool only not on home page)" | [ae136393](https://github.com/CorentinTh/it-tools/commit/ae1363937bf3) (PR #1368, 2024-10-25) | `/token-generator` |

### 2. react-admin e-commerce demo (`marmelab/react-admin`, MIT, ~27k stars)
"Posters Galore", the admin app react-admin ships as its demo (`examples/demo`): orders, customers,
products, reviews, a dashboard. Its data is generated in the browser by the repo's own data
generator and served by a fake REST server in the page, so nothing leaves the Mac; sign-in takes
any user name (the login page offers `demo` / `demo`). Vite resolves react-admin's packages from
source, so `yarn install` then `yarn dev` in `examples/demo` is enough. These bugs live in a real
framework many companies build on, two of them reported against this very demo.

| Bug | Issue (reporter's words, shortened) | Fixed by | Start page |
|---|---|---|---|
| RA-1 | [#10192](https://github.com/marmelab/react-admin/issues/10192) "Go to the Orders list … click on the 'add filter' button and select the 'clear filters' dropdown … The list empties" (expected: all records) | [5fa05d4b](https://github.com/marmelab/react-admin/commit/5fa05d4ba037454a5a1256748c48983ce3794f5c) (PR #10193, 2024-09-10) | `/#/orders` |
| RA-2 | [#10136](https://github.com/marmelab/react-admin/issues/10136) "When navigating to the show page from the second page or later in a paginated list, the `PrevNextButtons` component should display the correct index" (it doesn't) | [22dae61e](https://github.com/marmelab/react-admin/commit/22dae61e51a880e9160cb7083f64d04849c04f78) (PR #10144, 2024-08-14) | `/#/orders` (the order page has the buttons) |
| RA-3 | [#9468](https://github.com/marmelab/react-admin/issues/9468) TabbedForm: "The tabs beyond the first one are not reachable, instead the first tab keeps being visible … the url keeps adding the index of the clicked tab" | [2bed8b22](https://github.com/marmelab/react-admin/commit/2bed8b2244a9d25ecf227e58f857639b7edc5e26) (PR #9480, 2023-11-29) | `/#/products` (a product's edit page is a TabbedForm) |

**Start page (decided without the owner, revisit):** each run starts on the page of the feature
the bug is in, with no description of the bug and no focus text, like a team asking for a test
of one feature after a change. Starting at IT-Tools' home page (80 tools) would mostly measure
whether 40 steps happen to open the right tool. The agent still has to find the trigger itself
(type an invalid numeral, pick RC4 in the right panel, page through orders, ...).

**Reserve:** IT-Tools [#283](https://github.com/CorentinTh/it-tools/issues/283) (OTP generator
rejects a lower-case secret, fixed by 7c40539e) and react-admin
[#10667](https://github.com/marmelab/react-admin/issues/10667) (dashboard chart in € with $
tooltips, fixed by 9d23f078), if a bug above doesn't reproduce.

## Method

(Filled in as the benchmark is built: the fetch-and-start script, the reproduction checks, how a
report is matched to the real bug, and what "reached" means.)

## Results

(Filled in after the measurement.)

## Honest limits

(Filled in after the measurement.)
