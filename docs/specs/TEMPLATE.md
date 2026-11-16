# Specs template: the holdout app (apps/demo2, "Harbour guesthouse")

**For the owner to fill in, as a QA engineer would**: write the app's *intended* behaviour from
what a guesthouse booking site should do, without looking at `apps/demo2/bugs.json` or the
`bug(...)` switches in the source. Save the result as `apps/demo2/specs.md` (Markdown or plain
text; user stories and acceptance criteria, in any style you'd use at work).

This template only names the pages and features that exist. It deliberately says nothing about
how they should behave: that is the part the specs add. A guard test fails if a spec line closely
matches a planted-bug description, so write requirements, not the bugs you remember.

Suggested shape for each feature:

```
### <feature>
As a <guest>, I want <...> so that <...>.
Acceptance criteria:
- Given <...>, when <...>, then <...>.
```

## Page: Rooms (`/`)
- Room list (name, short description, link to each room)

## Page: Room (`/rooms/:id`)
- Room details: name, description, how many it sleeps, price per night
- Availability (shown next to the price)
- Booking form, fields:
  - Guest name
  - Email
  - Check-in date
  - Check-out date
  - Phone (optional)
- Stay summary: number of nights, price per night, total
- "Book now" button and the confirmation after booking
- A room id that doesn't exist

## Page: My bookings (`/bookings`)
- List of the guest's bookings (room, guest, dates, total)
- Empty state

## Across the site
- Navigation between Rooms and My bookings
- Pages that don't exist
- Phone-sized screens
- Accessibility (labels, keyboard use)
