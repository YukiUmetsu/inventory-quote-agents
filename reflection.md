# Reflection

## Architecture and Design Decisions

I implemented the system as a five-agent workflow using PydanticAI:

1. **Orchestrator Agent** – coordinates the overall workflow and delegates work to the other agents.
2. **Inventory Agent** – checks whether requested products exist, verifies current stock, determines shortages, and evaluates whether missing inventory can be replenished before the customer's deadline.
3. **Commercial Agent** – generates quotes and finalizes accepted sales.
4. **Customer Agent** – simulates the customer's response to a quote and supports limited negotiation.
5. **Business Advisor Agent** – analyzes internal inventory and financial information and provides operational recommendations.

I chose this architecture because each agent has a distinct responsibility. The Orchestrator controls the process rather than allowing agents to call each other freely. This makes the workflow easier to reason about and helps prevent duplicated inventory checks, repeated sales, or excessive negotiation.

The typical workflow is:

Customer Request
→ Inventory Agent
→ Commercial Agent for quote
→ Customer Agent
→ Commercial Agent for sale if accepted
→ optional Business Advisor analysis

If the Inventory Agent determines that the complete order cannot be fulfilled, the workflow stops before quoting or creating transactions.

I also used shared request state to track information such as the request date, delivery deadline, quote rounds, customer negotiation rounds, quoted items, and whether a sale was completed. This helps prevent repeated operations and allows the final sale to use the authoritative quote rather than allowing the language model to invent prices.

The agent tools combine the starter helper functions with business rules. For example, inventory checks use stock levels, supplier delivery dates, and available cash, while quote generation applies a deterministic bulk-discount policy and consults historical quote data when available.

## Evaluation Results

I evaluated the system using the full `quote_requests_sample.csv`
dataset containing 20 customer requests.

In the final test run:

- **5 requests were successfully fulfilled**
- **5 requests resulted in a change to the cash balance**
- **15 requests were not fulfilled**
- Every unfulfilled request included an explanation of why the complete
  order could not be processed

The fulfilled requests were requests 1, 4, 6, 10, and 12.

The successful requests demonstrated that the system could handle both
orders that could be fulfilled from available inventory and orders that
required feasible inventory replenishment.

The rejected requests demonstrated several expected failure conditions,
including:

- products that were not in the company catalog
- insufficient inventory
- supplier replenishment that could not arrive before the customer's
  required delivery date
- orders where only part of the requested products could be supplied

The workflow also behaved consistently in the final evaluation.
Requests that failed inventory feasibility stopped before quote
generation, while successful requests proceeded through inventory
assessment, one quote round, customer evaluation, and sales
finalization.

These results satisfy the evaluation requirements because more than
three requests were fulfilled, more than three requests changed the
cash balance, and the system did not incorrectly fulfill every request.

## Strengths

One strength of the system is that important business decisions are handled by deterministic tools rather than by the language model alone. Inventory quantities, supplier dates, transactions, and quote prices are calculated using Python functions and database data. The agents mainly interpret requests and coordinate those tools.

Another strength is that quote generation uses a consistent bulk-discount policy and historical quote information rather than allowing the Commercial Agent to invent prices.

The system also prevents several unsafe workflow behaviors. Inventory assessment is performed once per request, sales can only be finalized after an accepted quote, and the accepted quote is stored in shared state so the sale uses the original quoted quantities and prices.

Customer-facing responses generally explain why an order succeeds or fails without exposing internal cash balances, profit information, database details, or transaction IDs.

The Customer Agent also adds a negotiation step based on the customer's request context, which makes the workflow more realistic than automatically accepting every generated quote.

## Areas for Improvement

### 1. Profitability-aware pricing

The current quote policy applies deterministic bulk discounts based
primarily on order quantity. In the final evaluation, some successfully
fulfilled orders produced a negative request-level cash change because
the cost of replenishing inventory exceeded the revenue collected from
the discounted sale.

A future version should consider procurement cost when generating a
quote and enforce a minimum contribution margin before applying a bulk
discount. This would prevent feasible orders from being accepted at
prices that are operationally unprofitable.

### 2. Product substitutions

The current workflow rejects the complete order when a required product
is unsupported or cannot meet the delivery deadline.

A future version could identify appropriate catalog substitutes and
allow the Customer Agent to negotiate those alternatives. For example,
the system could suggest a supported paper size or paper type rather
than immediately rejecting an order containing an unsupported product.

### 3. More structured agent outputs

The business-critical calculations are deterministic, but agents still
produce natural-language responses and make some orchestration
decisions through the language model.

A future version could use Pydantic response models for inventory
decisions, quotes, negotiation decisions, and sale results. This would
make agent-to-agent communication more deterministic and easier to
validate automatically.

### 4. More detailed fulfillment and accounting state

The starter transaction model uses a relatively simple representation
of stock purchases and sales. A production system should separately
track purchase date, supplier arrival date, customer order date,
fulfillment date, and delivery date.

Separating these concepts would provide more accurate inventory and
cash-flow accounting.

## Conclusion

The final system successfully coordinates multiple specialized agents while keeping important inventory, pricing, and transaction decisions grounded in deterministic tools and database data.

The evaluation shows that the system can successfully fulfill feasible requests while rejecting orders that contain unsupported products or impossible delivery constraints. The main opportunities for improvement are more sophisticated profitability-aware pricing, better substitution handling, and more structured agent outputs.