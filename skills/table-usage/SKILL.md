---
name: table-usage
description: "Database table and view reference — describes available data sources and their purposes to help agents write accurate SQL queries."
---

# Table Usage Reference

Use this reference BEFORE writing SQL queries to understand what data sources are available and which table or view is most relevant to the user's question.  The table names schemas, and a selection of columns are already provided in the user profile, but this reference provides additional context and descriptions to ensure accurate query generation.

## How to Use

When a user asks a question that may require SQL:
1. Review the tables/views listed below to find the most relevant data source.
2. Note the column descriptions to build accurate queries.
3. If no table matches the user's request, state that clearly.


### Example: users
| Column | Type | Description |
|--------|------|-------------|
| id | int | Primary key |
| name | varchar | User display name |
| email | varchar | User email address |
| created_at | datetime | Account creation timestamp |

### Example: orders
| Column | Type | Description |
|--------|------|-------------|
| id | int | Primary key |
| user_id | int | Foreign key to users |
| total | decimal | Order total amount |
| status | varchar | Order status (pending, completed, cancelled) |
| created_at | datetime | Order creation timestamp |
