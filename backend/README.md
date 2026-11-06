my_fastapi_app/
│
├── app/
│   ├── __init__.py
│   ├── main.py                  # App initialization, middleware, & lifecycle events
│   ├── config.py                # Pydantic settings management
│   │
│   ├── api/                     # Presentation Layer (Routes & Controllers)
│   │   ├── __init__.py
│   │   ├── deps.py              # Common route dependencies (Auth, DB session)
│   │   └── v1/
│   │       ├── router.py        # Master v1 router aggregator
│   │       └── endpoints/
│   │           ├── users.py     # User-facing endpoints
│   │           └── items.py     # Item-facing endpoints
│   │
│   ├── services/                # Domain Layer (Business Logic)
│   │   ├── __init__.py
│   │   ├── user_service.py      # Core user validation & workflows
│   │   └── item_service.py
│   │
│   ├── repositories/            # Data Access Layer (DB Interactions / CRUD)
│   │   ├── __init__.py
│   │   ├── base.py              # Generic CRUD repository
│   │   ├── user_repo.py         # User-specific database operations
│   │   └── item_repo.py
│   │
│   ├── models/                  # Database Models (SQLAlchemy/SQLModel)
│   │   ├── __init__.py
│   │   ├── user.py
│   │   └── item.py
│   │
│   └── schemas/                 # Data Transfer Objects (Pydantic Models)
│       ├── __init__.py
│       ├── user.py              # UserIn, UserOut, UserUpdate
│       └── item.py
│
├── database/                    # Connection & Migration Setup
│   ├── session.py               # Async Engine & Sessionmaker
│   └── base_model.py            # Declarative Base class
│
├── tests/                       # Pytest Test Suite
├── .env                         # Environment variables
├── Dockerfile
└── requirements.txt

After an LLM play event, the UI should call GET /queue to refresh it. Searching alone doesn’t change the queue
