# ToS alerts -> Notion E Signals log (email + Zapier)

Every JournalTriggers signal becomes a row in the Notion **E Signals** database, with no typing.

## What gets filled automatically
- Signal (title), Date/time, Setup, Direction and Alert text.

## What stays manual
- Entry, Stop, T1, Result, Exit, Points, Taken, Followed rules, the Bookmap columns and the screenshot.
- thinkScript alert text must be fixed text (`Alert()` rejects prices with "Only constants expected here"), so prices can't travel in the alert.

## 1. thinkorswim
1. Re-import `thinkorswim/JournalTriggers.ts` (or `JournalTriggersLite.ts`). The alerts now read, for example:
   `JT | Sweep S | Short | check Bookmap`
   The setup names match the Notion options exactly: Sweep S/L, Fail BO S/L, BB fail S/L, HTF S/L, VAH flip S, VAL flip L, POC loss S, POC reclaim L.
2. Study inputs for E: `winStart = 1030`, `winEnd = 1100` (failed breakouts still fire until `fboEnd` 13:00).
3. Turn on email for study alerts:
   - Go to **Setup -> Application Settings -> Notifications**.
   - Enter the email address from step 2 below (or your own address, then forward it, see the tip at the end).
   - Tick email for the alerts that studies trigger. Labels vary between ToS versions.
4. `Alert()` runs on your computer: ToS must be open, with the /ES 5-minute chart and the study loaded, during the session. Server-side (MarketWatch) alerts can't run a study this size.

## 2. Zapier (free plan is enough: 2 steps, about 2-10 signals a week)
1. **Email Parser by Zapier** (parser.zapier.com): create a mailbox. You get an address like `something@robot.zapier.com`.
2. Send a test email to it with the body:
   `JT | Sweep S | Short | check Bookmap`
3. In the parser, highlight `Sweep S` and name it **setup**, then highlight `Short` and name it **direction**. Save the template.
4. New Zap:
   - **Trigger:** Email Parser by Zapier -> New Email (your mailbox).
   - **Action:** Notion -> Create Data Source Item (Create Database Item in older Zapier).
   - Connect Notion and give the Zapier connection access to the **Forward Test: Journal Triggers E** page.
   - Database: **E Signals**. Map the fields:

   | Notion property | Zapier field |
   |---|---|
   | Signal | `setup` (or Date + setup) |
   | Date | email Date / Received |
   | Setup | `setup` |
   | Direction | `direction` |
   | Alert text | Body (plain) |

5. Test the Zap with the sample email. A row should appear in E Signals with Setup and Direction set.

## Tips
- To keep your own copy, send ToS alerts to your Gmail, and add a filter that forwards emails containing `JT |` to the parser address. Gmail asks you to confirm the forwarding address once.
- After each session, open the **All signals** view and fill in the manual columns on the new rows.
- If a row's Setup shows a new grey option, the alert text and the parser template have drifted apart. Re-check step 3.
