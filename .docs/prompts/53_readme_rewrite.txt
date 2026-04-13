rewrite README.md for the svp_mic project.

read the following files before writing:
- README.md
- .claude/context.md
- .claude/adr.txt
- docker-compose.yml
- nginx/nginx.conf
- shared/exceptions.py
- planning_service/services/plan_service.py
- planning_service/outbox/poller.py
- planning_service/consumers/customer_events.py
- planning_service/projections/plan_projection.py
- expense_service/projections/expense_projection.py
- expense_service/services/expense_service.py
- customer_user_service/consumers/plan_confirmed.py
- customer_user_service/producers/customer_deactivated.py
- tests/conftest.py

the README must cover the following sections in order:

1. project overview
   what SVP is, the business problem it solves, and the three actors:
   sales rep, manager, and admin. keep this concise and factual.

2. architecture
   the four backend services (customer_user_service, planning_service,
   expense_service, frontend_service), the nginx gateway, Kafka,
   Redis, and the three PostgreSQL databases. explain the
   database-per-service principle and why there are no cross-service
   foreign keys. include the internal container names and ports.

3. patterns implemented
   cover all three patterns in depth:

   saga — explain what the saga pattern is, then describe exactly how
   it is implemented here. the day plan confirmation saga starts in
   planning_service when a plan is confirmed, publishes plan.confirmed
   via the outbox, and customer_user_service consumes it to verify
   customer activity. the customer deactivation saga starts in
   customer_user_service, publishes customer.deactivated, and
   planning_service rolls back any active or confirmed plans.

   transactional outbox — explain the pattern and why it guarantees
   at-least-once delivery. describe the Outbox model in
   planning_service/models.py, the poller in outbox/poller.py, and
   how the outbox insert is made atomically with the state change in
   the same database transaction in confirm_plan.

   CQRS — explain the pattern and the read/write model separation.
   describe how update_plan_projection and update_expense_projection
   are called synchronously after every state change, and how the
   read-side endpoints in plans_read.py and expenses_read.py serve
   denormalised summaries without touching the write-side tables.

4. kafka topics and event flows
   a table listing each topic, the producing service, the consuming
   service, and what triggers the event. topics are: plan.confirmed,
   plan.rolled_back, customer.deactivated, expense.submitted,
   expense.decided.

5. api endpoints
   a table per service listing HTTP method, path, and a one-line
   description. cover customer_user_service, planning_service, and
   expense_service. do not include frontend_service routes.

6. running the stack
   prerequisites, the docker compose up --build command, and a note
   about the .env file.

7. running the tests
   how to create the venv, install pytest httpx pytest-asyncio, and
   run pytest tests/. note that the stack must be running first.

8. directory structure
   a brief prose description of the top level layout referencing the
   tree output. do not reproduce the full tree.

write in clear technical prose. no marketing language. use markdown
headings and tables where they genuinely aid readability. prose
paragraphs for explanatory sections, tables for structured reference
data.