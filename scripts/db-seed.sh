#!/usr/bin/env bash
# Seed database with initial data (admin user, default project, etc.)

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/.env"

cd "$ROOT/backend"
source "$ROOT/.venv/bin/activate"
set -a; source "$ROOT/.env"; set +a
export PYTHONPATH="$ROOT/backend${PYTHONPATH:+:$PYTHONPATH}"

python << 'PYEOF'
import asyncio
import uuid
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from infrastructure.config import settings
from infrastructure.db.models import User, Project, StyleLibrary
from domain.enums import LibraryCategory

async def seed():
    engine = create_async_engine(str(settings.database_url))
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Check if admin exists
        result = await session.execute(select(User).where(User.email == "admin@admin.com"))
        admin = result.scalar_one_or_none()
        
        if not admin:
            admin = User(email="admin@admin.com", full_name="Admin", is_active=True)
            session.add(admin)
            await session.flush()
            print(f"Created admin user: {admin.id}")
        else:
            print(f"Admin user exists: {admin.id}")
        
        # Check if default project exists
        result = await session.execute(select(Project).where(Project.name == "Default"))
        project = result.scalar_one_or_none()
        
        if not project:
            project = Project(name="Default", owner_id=admin.id, description="Default project")
            session.add(project)
            await session.flush()
            print(f"Created default project: {project.id}")
        else:
            print(f"Default project exists: {project.id}")
        
        # Check if default library exists
        result = await session.execute(select(StyleLibrary).where(StyleLibrary.name == "Default Library"))
        library = result.scalar_one_or_none()
        
        if not library:
            library = StyleLibrary(
                name="Default Library",
                category=LibraryCategory.OTHER,
                owner_id=admin.id,
                project_id=project.id,
                language="en",
                status="active",
                version=1,
                is_single_voice=False
            )
            session.add(library)
            await session.flush()
            print(f"Created default library: {library.id}")
        else:
            print(f"Default library exists: {library.id}")
        
        await session.commit()
        print("Seed complete.")
    
    await engine.dispose()

asyncio.run(seed())
PYEOF
