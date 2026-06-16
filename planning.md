# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
the 3 listings 2 are optional the first listing is the main key. It finds best first match and gives a list back if no match empty list.
**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `description` (str): ...
primary tool used to match search
string
- `size` (str): ...
optional filter to help match 
string
- `max_price` (float): ...
another optional filter to complete the corect match
string

**What it returns:**
<!-- Describe the return value — what fields does a result contain? -->
list

**What happens if it fails or returns nothing:**
<!-- What should the agent do if no listings match? -->
empty list []

---

### Tool 2: suggest_outfit

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
takes listing dict also a adds wardrobe. Then goes and ask the LLM.
**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `new_item` (dict): ...
type dict and the list 
- `wardrobe` (dict): ...
dict list of items

**What it returns:**
<!-- Describe the return value -->
returns a string
**What happens if it fails or returns nothing:**
<!-- What should the agent do if the wardrobe is empty or no outfit can be suggested? -->
suggest a new item
---

### Tool 3: create_fit_card

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
turns the outfit suggestion into a shareable caption
**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `outfit` (...): ...
listing dict string 
**What it returns:**
<!-- Describe the return value -->
string
**What happens if it fails or returns nothing:**
<!-- What should the agent do if the outfit data is incomplete? -->
print an error message.
---

### Additional Tools (if any)

<!-- Copy the block above for any tools beyond the required three -->

---

## Planning Loop

**How does your agent decide which tool to call next?**

Overview:
- The Planning Loop is a deterministic controller that inspects `session_state` and the current user query, chooses the next action (tool call, follow-up question, or final response), and writes both inputs and outputs to `session_state`.
- The loop is orchestrated by a small decision function `next_step(session_state)` that returns one of: `call_search_listings`, `call_suggest_outfit`, `call_create_fit_card`, `ask_user_clarification`, or `finish`.

Decision inputs:
- `session_state.constraints`: parsed search filters (keywords, size, price). If missing, the planner attempts lightweight extraction from `user_query`.
- `session_state.listings`: empty → triggers `call_search_listings`; non-empty but `selected_item` missing → planner selects candidate and triggers `call_suggest_outfit`.
- `session_state.selected_item` and `session_state.wardrobe`: both present → trigger `call_suggest_outfit`.
- `session_state.outfit_suggestion`: present and validated → trigger `call_create_fit_card`.
- `session_state.fit_card`: present → trigger `finish`.

Heuristics and ordering:
- Primary path: parse query → search_listings → pick selected_item → suggest_outfit → create_fit_card → finish.
- If `search_listings` returns multiple results, planner ranks by keyword match score, price proximity (<= max_price preferred), and freshness; top result stored in `selected_item`, extras remain in `listings` for fallback.
- If `wardrobe` is missing, the planner will still call `suggest_outfit` with `selected_item` but mark `wardrobe_missing=true` in `session_state` so suggest_outfit uses conservative defaults.

Failure handling in the loop:
- If `search_listings` returns an empty list, planner sets an error entry in `session_state.errors` and either (a) relaxes constraints (wider keywords or higher price) and retries up to N times, or (b) asks the user a clarifying question when automated relaxations fail.
- If `suggest_outfit` returns no viable outfit, planner records the failure, falls back to a short, rule-based styling tip (e.g., "wear with high-waist jeans and white sneakers"), and proceeds to `create_fit_card` with that fallback text.
- If `create_fit_card` fails due to incomplete input, planner reconstructs a minimal outfit object from `selected_item` and fallback styling and retries once; if still failing, planner asks user to clarify required fields.

Termination conditions (`finish`):
- `session_state.fit_card` exists and `session_state.errors` contains no blocking errors.
- Or planner has produced a usable fallback card after allowable retries.

Follow-up questions and user interaction:
- The loop may return `ask_user_clarification` when ambiguity cannot be resolved automatically (ambiguous size, conflicting constraints, or required metadata missing). Clarifying questions are short and specific (e.g., "Do you prefer oversized or fitted?"), and user answers are merged into `session_state.constraints`.

Example pseudo-flow (high level):
1. Parse query → set `constraints`.
2. `next_step()` → `call_search_listings`.
3. `search_listings` writes `listings` (or empty) to state.
4. If listings present → planner selects top match → set `selected_item` → `next_step()` → `call_suggest_outfit`.
5. `suggest_outfit` writes `outfit_suggestion` → `next_step()` → `call_create_fit_card`.
6. `create_fit_card` writes `fit_card` → `next_step()` → `finish` → build final response from `fit_card` + brief listings summary.

Notes on implementation:
- Keep `next_step()` simple and pure (no external calls) to make unit testing straightforward.
- Record timestamps and versioned snapshots in `session_state` for debugging and reproducibility.


---

## State Management

**How does information from one tool get passed to the next?**
The agent uses a single session_state dictionary that is updated after every tool call. The planning loop never passes raw tool outputs directly to the next tool. Instead, each tool writes normalized data into session_state, and the next tool reads from that state.

Data tracked in session_state:
- user_query: original user message
- constraints: parsed search filters such as description keywords, size, and max_price
- listings: candidate items returned by search_listings
- selected_item: the best listing chosen for styling
- wardrobe: user wardrobe data provided in the prompt or profile
- outfit_suggestion: structured outfit returned by suggest_outfit
- fit_card: final formatted output from create_fit_card
- errors: list of tool failures and fallback actions taken

Tool-to-tool handoff flow:
1. Planning loop parses the user query and stores filters in constraints.
2. search_listings reads constraints and returns listings. The loop stores results in listings.
3. Planning loop selects one listing (selected_item) and combines it with wardrobe from state.
4. suggest_outfit reads selected_item + wardrobe and returns outfit_suggestion, which is saved.
5. create_fit_card reads outfit_suggestion and returns fit_card text/object, which is saved.
6. Final user response is built from listings summary + outfit_suggestion + fit_card.

If any tool fails, the planner writes the failure to errors and either retries with adjusted input or takes a fallback path. Because state is centralized, retries can reuse prior results instead of recomputing from scratch.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | |
| suggest_outfit | Wardrobe is empty | |
| create_fit_card | Outfit input is missing or incomplete | |

---

## Architecture

```mermaid
flowchart TD
     U[User Query]\n+    P[Planning Loop]\n+    S[(Session State)]\n+    O[Final Response to User]\n+
     T1[search_listings\n+input: description, size, max_price]
     T2[suggest_outfit\n+input: new_item, wardrobe]
     T3[create_fit_card\n+input: outfit]

     E1[No listing matches]\n+    E2[Wardrobe empty or no outfit match]\n+    E3[Outfit data incomplete]\n+
     U --> P

     P -->|parse intent + constraints| T1
     T1 -->|results[]| P
     T1 -->|empty results| E1
     E1 -->|relax filters / ask user follow-up| P

     P -->|choose top listing + wardrobe context| T2
     T2 -->|outfit suggestion| P
     T2 -->|no outfit| E2
     E2 -->|fallback styling tips with available items| P

     P -->|validated outfit object| T3
     T3 -->|fit card text| P
     T3 -->|missing required fields| E3
     E3 -->|rebuild outfit object or ask clarification| P

     P -->|done condition: listing + styling + card ready| O

     P <--> |read/write: user prefs, query constraints, candidate listings, selected item, wardrobe snapshot, outfit draft, fit card, error flags| S
     T1 <--> |cache search query + results| S
     T2 <--> |store selected item + outfit candidate| S
     T3 <--> |store final card payload| S
```

---

## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->
     "what was used by claude was first an understanding of the tool and examples of what the tool can do with different approaches. Then once the function was understandable claude was asked to give a implemantation of what this example that was picked would look like. the planning was looked at carefull each step to then pick the best solution.

**Milestone 3 — Individual tool implementations:**


**Milestone 4 — Planning loop and state management:**

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**
<!-- What does the agent do first? Which tool is called? With what input? -->
searching_listings function
**Step 2:**
<!-- What happens next? What was returned from step 1? What tool is called now? -->
gets sent to 
**Step 3:**
<!-- Continue until the full interaction is complete -->
suggest_outfits
**Final output to user:**
<!-- What does the user actually see at the end? -->
create_fit_card