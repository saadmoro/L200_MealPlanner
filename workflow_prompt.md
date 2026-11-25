# Recipe Planner Agentic Workflow

Using Google ADK 2.0, we will design an agentic workflow for a hypothetical grocery store that helps customers plan meals and shopping lists. 

Customers interact with the grocery store's systems in order to follow healthy meal plans, and to plan their shopping trips. The system can develop knowledge of the customer and their dietary needs (i.e. some customer ID is named Malcom Munson, has celiac disease and high blood pressure, likes mediterranean food, prefers chicken to fish), or may be used simply to generate recipes if there are no special resrictions or needs. Users might still have food preferences, such as a distaste for eggplants or spicy food. These should all be kept in agent memory, associated with the user. The user might also express an interest for easier or more advanced recipes, depending on their experience as a cook, which should also be recorded and influence the complexity of recipes offered to the user.

When the user accesses the agent, they should be met with a friendly message, such as "Hello! What are you hungry for?". They should be given the option to enter a specific meal they want to eat (i.e., "kung pao chicken"), or be helped to decide on a meal that meets their taste by asking them questions and offering suggestions. This section is gated by the user selecting a meal to eat.

Next, we need to appropriately size the meal, and offer nutrition guidance. Each meal should have an approximate serving size and calorie count, along with information for several macronutrients, such as protein, fats, and carbs, while also serving dietary needs (vegetarian, low sodium, gluten free, etc). The user also needs to choose how many meals they want to eat: we'll need to purchase different amounts of ingredients if the customer wants to eat this meal 4 times, versus 2 times. 

Once we have a recipe and volume, we need to create a meal item, which is a list of specific items in the grocery store's inventory, and how much needs to be purchased in order to make the chosen meal. For example, we may need to purchase 1.5 lbs of chicken, 2 oz of butter, 3 bell peppers, and so on. Again, the user should be given the option to remove items if they don't want them on their shopping list.

Finally, the user can be "sent" the shopping list. For the time being, we should simply attach their finalized list of inventory items and their selected recipe to their account, but eventually this might be sent to their phone via SMS, or appear in some kind of user-facing application. We will send a final message that includes both their shopping list and the complete recipe that the user chose to follow, .

Always prefer deterministic tool use over probabilistic agent calls. When it is possible, create tools which can offer deterministic results. 

The grocery store manages several databases, that you will need to generate in order to create this workflow.

- Product catalogue database
- Nutritional facts
- Inventory
- User information

Offer example schemas for each data base before we decide on them. User information will likely be created and tested using a suite of tests, but the product catalogue, inventory, nutrition facts, etc will need to be databases with enough entries.

We should have tools to return lists of items (primary key being an SKU), convert to calories (could be related to nutrition facts associated with an individual product item) or portion size, etc. 

When the user accepts a given recipe, or meal plan, a set of ingredients will be provided to them. They will have the option to deselect certain items in case they already own them (i.e., a recipe calls for cumin powder, which the customer says they already have). In practice, they might forward their shopping list to their associated phone number or mobile app, but we can assign a new entry in a purchase database. 

There are 5 core areas that we need to master with this agent. Before we begin, create a design document which proposes an approach to each of the following 5 areas using tools within the Google Agent Development Kit 2.0 framework. We'll iterate on the plan before executing. If there are any special requirements or ideas of my own, they will be listed after the problem area. 

1. Tool and Interface Design:
The application should be user-friendly, and where determinism is a possibility, should offload work to tools. We might create a UI for the application once the core logic is nailed.

2. Orchestration and Logic

3. Context and Memory:
Memory should be restorable across sessions.

4. Observability and Tracing:
We want full OpenTelemetry style traces, and should be able to trace back every decision, tool call, and state transition made by agents.

5. Infrastructure and CI/CD:
Follow best practices for agentic applications. We will treat every system prompt, agent, tool, etc as something under version control.

Your task is to first plan out how to develop an agentic application with Google ADK 2.0 that addresses the above situation and workflow, offering suggestions where applicable to improve the user experience, and which is exemplary in the 5 graded areas above. Create example workflow diagrams to show the flow of data / the agentic DAG. Feel free to import packages, libraries, etc (you will probably want SQLite, for example).

Write a planning document to file, rending in HTML if that would be helpful. We will begin implementation once the plan is decided upon.

If you have any clarifying questions, please ask.