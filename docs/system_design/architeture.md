# Architecture

## 1. Client - Service - Permanent Storage

```mermaid
graph TD
    %% Styling and layout

    subgraph Client
        %% direction LR

        Web[Web Applicaiton]
        Mobile[Mobile Application]
    end

    Client -->|HTTPS| LoadBalancer[Load Balancer]

    Client --> |HTTPS| CDN

    subgraph Entrance
        LoadBalancer --> APIGateway[API Gateway]
        CDN[CDN]
    end
    
    subgraph Services
        
        APIGateway --> ApplicationService[Application Services]
        ApplicationService --> Model[Model]


        ApplicationService --> AsyncProcessing[Async Processing]

        AsyncProcessing --> Model
    end

    subgraph Storage
        Model --> DB[(Primary Database)]
        Model --> Cache[(Redis Cache)]
    end

    classDef database fill:#f9f,stroke:#333,stroke-width:2px;
    class DB,Cache database;
```

## 2. Tech-Stack

### Frontend 

- React + Next.js (~55% - 60%)

### Backend 

- Python + FastAPI

### Database

- PostgreSQL

### API

- RESTful API

## 3. Backend 

### Services

- Application Services + Domain + Repository / DAO

### Database

- PostgreSQL