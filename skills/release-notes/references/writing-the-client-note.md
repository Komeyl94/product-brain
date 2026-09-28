# Writing the client note

The client note is often the only document a paying customer reads without
anyone from the team in the room. It has one job: tell a person what they can now
do — and enough about why it helps that they can decide whether to care.

**It is written in one language: `releases.client_note.locale`.** There is no
second half. The verifier fails any other `<article data-lang>`, so a translation
cannot quietly reappear and drift.

## Take every product noun from the client-locale i18n file

Write the note from the screen the client sees, never from another language and
never from the commit messages. When a product's languages are authored
separately, the value at one key is often a different idea in each. An
illustration, with Persian as the client locale and English as the source - the
pattern is what matters, not the product:

| Key | Source (en) value | Client (fa) value | Literal back-translation |
|---|---|---|---|
| `profile.background` | Experience | پیشینه کاری | *work background* |
| `share.others` | For family and friends | برای خانواده یا دوستان | *for family or friends* |
| `list.load-again` | Load again | تلاش مجدد | *try again* |
| `list.empty` | Nothing here yet | موردی ثبت نشده است | *no item has been recorded* |
| `settings.columns.otp` | OTP | رمز یکبار مصرف | *one-time password* |

A note that reads the source key and renders it into the client language will
name a button the client's UI does not have. The last row shows why it matters in
both directions: the source screen says the jargon this note is forbidden to use,
while the client screen already says the plain-language phrase.

**So:** for every item, open the changed keys in `facts.repos[].i18n` and take the
noun from the **`client`** value. Where a key has a `source` value and no `client`
value, that is an i18n gap and a finding for the *internal* note — not something
to paper over by translating it yourself.

## The card recipe

A **new feature** is four parts, and only the first two are required:

```
<b>          {the thing, named as the client-locale UI names it}
.benefit     {two or three sentences: what a person can now do, and what it saves them}
.scenario    {one concrete situation - optional, never invented}
.where       {where to find it, in the words the menu uses}
```

An **improvement** is still two parts, because it is one line of news:

```
<b>          {the thing}
<span>       {what stopped going wrong}
```

Test each card against: *could someone who has never seen the codebase read this
and know whether it affects them?* If it needs an engineer to decode, rewrite it.

### Writing the benefit

Two or three sentences, and they answer different questions. The first says what
is now possible. The second says what it costs or saves — the consequence
somebody will actually notice. A third, if there is one, covers what happens at
the edges: the empty state, the warning, the thing that does not change.

| Weak | Why | Better |
|---|---|---|
| "You can now choose a notification channel." | restates the title | "One page lists all four channels side by side, and each has two separate switches: one for notifications and one for sign-in codes. So you can get due-date reminders by email and your sign-in code by text." |
| "Added support for a messaging app." | says who did the work, not what changed | "Link your account once and from then on notifications and sign-in codes arrive there. Unlink it whenever you like; sending stops at once." |
| "Reminder settings improved." | no observable difference | "An admin decides which reminders go to members and which to guests — each kind separately. For workspaces that sent everything until today, nothing changes." |

**Say what does not change.** "Everything starts switched on, and stays that way
until someone changes it" is the sentence that stops a support ticket. It is also
the sentence nobody thinks to write.

### Writing the scenario

One person, one situation, one outcome, in the second person, and *specific* —
the point is recognition, not illustration.

> **For example,** your email is open all day and you see texts late. You switch
> email notifications on and text notifications off — but keep the text sign-in
> code on, because at sign-in it is the fastest route.

Rules:

- **Never invent one.** If you cannot describe a real use of the feature, the
  card is better without a scenario than with a fictional one. Inventing a
  scenario is how a release note starts describing a product that does not exist.
- **Pick a situation the reader would recognise** — their market, their
  constraints (a country where texts arrive late, a phone with no signal but
  working internet). Not a translated example.
- **No numbers you have not checked.** No "three fewer clicks".

### Writing the screenshot's words

A picture needs two pieces of copy, and they are not the same sentence:

- **`alt`** — for someone who cannot see it. Describe what the screen *contains*:
  "Four rows — text, email, and two messaging apps — each with two switches".
  Never "screenshot of the settings page".
- **`figcaption`** — for someone who can. Point at what matters in the picture
  and connect it to the copy: "each row is a channel and each column a kind of
  message". It should tell the reader what to notice, not repeat the alt text.

Both describe the **client-locale** screen, because that is what the capture
shows and what the reader will open.

### Worked examples

Improvement-sized items, where one line is the whole story:

| Change (internal wording) | Client wording |
|---|---|
| paginate activity history, fix card alignment | Your activity history is now shown in pages, neatly aligned. |
| parse end-time explicitly, flag midnight crossover | Events that run past midnight show the right end time. |
| add optional default duration to projects | You can now set a default duration for each project. |
| correct weekly item count on dashboard | Your dashboard counts this week's items correctly. |
| fix(sonar): move test helpers into classes | *(nothing — invisible to the user, it does not appear)* |

That last row is the rule most often missed: **a change with no user-visible
effect does not get a client line.** It belongs in the internal note only. A
client note padded with invisible work reads as noise and trains people to stop
opening it.

## Words that must not appear

The verifier fails the file on these. It checks the English list whatever the
client locale, because technical English leaks into any language's copy far more
easily than it looks — a stray "endpoint" or "webhook" in a caption is the usual
way. Each locale can add its own transliterated list (`BLOCK_LOCAL` in the
verifier); Persian is the worked example there.

| Never | Say instead |
|---|---|
| endpoint, API, backend, frontend | name the screen or the action |
| deploy, deployment, pipeline, Docker, nginx | "update" |
| migration, schema, database, SQL, query | nothing — it is invisible |
| refactor, regression, exception, null | "this had stopped working" / "error message" |
| commit, branch, merge, repo, tag | nothing |
| cache, latency | "loads faster" |
| paginate, pagination | "shown in pages" |
| timestamp | "date and time" |
| token, JWT, OTP, RBAC | "sign-in code", "permissions" |
| framework and admin-panel names | "the admin area" |

## Typography for any locale

- **Dates** use `releases.client_note.calendar` (`gregorian` by default) in the
  client's digits where the locale has its own. `scaffold-note.py` computes them
  from `facts.releaseDate`.
- **Only what the embedded subsets carry will print.** Ordinary copy is covered;
  an arrow (`←`), a decorative bullet, a mathematical sign or a box-drawing
  character often is not, and the PDF silently falls back to a system face for
  the whole file. Write a word rather than an arrow. The PDF renderer names the
  offending character when this happens; widening the subset is a brand-system
  build change.
- **Identifiers a user reads back to support** — the version — stay in Latin
  digits, whatever digits the prose uses.

## When the client locale is RTL

Arabic-script and Hebrew notes (`releases.client_note.dir: "rtl"`) add rules the
verifier enforces only in that direction. Persian is the worked example.

- **Joiners are spelling.** Persian needs ZWNJ (U+200C) in words like
  می‌توانید، گزارش‌ها، به‌روزرسانی. A space instead of ZWNJ is a spelling error to
  a Persian reader. Other RTL scripts have their own equivalents; get them from
  the i18n file, never retype them.
- **An identifier is an LTR island.** A version next to RTL text gets reordered
  by the bidi algorithm unless wrapped: `<bdi dir="ltr">v1.2.3</bdi>`. The
  verifier fails an unwrapped version (the generic `v1.2.3` shape and anything
  matching `releases.tag_regex`). Native digits are right for counts inside a
  sentence, wrong for an identifier a user reads back to support. A Latin product
  name inside RTL copy is wrapped the same way by the scaffold.
- **`<bdi>` is not enough on its own — mind the separator.** A neutral character
  (`·`, `•`) between the LTR version and an RTL date resolves in the wrong
  direction and tears the date apart. Rendered side by side in Chrome, Persian:

  | Written | Renders as |
  |---|---|
  | `نسخهٔ <bdi dir="ltr">v1.2.3</bdi> · ۱۶ شهریور ۱۴۰۵` | the `۱` of the date torn off and parked by the version — **broken** |
  | `نسخهٔ <bdi dir="ltr">v1.2.3</bdi> — ۱۶ شهریور ۱۴۰۵` | correct |
  | `نسخهٔ <bdi dir="ltr">v1.2.3</bdi>‏، ۱۶ شهریور ۱۴۰۵` | correct — an explicit RLM (`U+200F`) after the `</bdi>` |

  Use an em dash, or an RLM. The verifier fails a `·` adjacent to a `<bdi>`.
- **The calendar may not be Gregorian.** Persian clients read Jalali dates
  (`calendar: "jalali"`); the scaffold converts and uses Persian digits.
- **Line height** is looser than a Latin page needs — the template sets `1.95` on
  an RTL note. Do not tighten it to fit more in.
- **The layout mirrors itself.** Logical properties only; never write `left` or
  `right` into the template.

## Encoding on the console

A Windows console in cp1252 **crashes** on non-Latin output:

```
UnicodeEncodeError: 'charmap' codec can't encode characters in position 13-14
```

That is a console limitation, not a data problem. Every script in this skill
reconfigures its own stdout to UTF-8, so its messages — including the verifier's,
which quote the text they found — print safely. For anything else:

- Write non-Latin text to **files**, with `encoding="utf-8"` given explicitly.
- Never verify it by echoing it to the terminal. Open the rendered HTML or the PDF
  and look at it.
