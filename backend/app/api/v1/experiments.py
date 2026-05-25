from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.session import get_db
from ...services.experiment_service import build_experiment_service


def _get_main_module():
    from ... import main
    return main


main = _get_main_module()
router = APIRouter()


async def create_experiment(experiment: main.Experiment, db: Optional[AsyncSession] = Depends(get_db)):
    service = build_experiment_service(main_module=main, db=db)
    return await service.create_experiment(experiment)


async def list_experiments(
    difficulty: Optional[main.DifficultyLevel] = None,
    tag: Optional[str] = None,
    username: Optional[str] = None,
    db: Optional[AsyncSession] = Depends(get_db),
):
    service = build_experiment_service(main_module=main, db=db)
    return await service.list_experiments(difficulty=difficulty, tag=tag, username=username)


async def get_experiment(experiment_id: str, db: Optional[AsyncSession] = Depends(get_db)):
    service = build_experiment_service(main_module=main, db=db)
    return await service.get_experiment(experiment_id)


async def update_experiment(
    experiment_id: str,
    experiment: main.Experiment,
    db: Optional[AsyncSession] = Depends(get_db),
):
    service = build_experiment_service(main_module=main, db=db)
    return await service.update_experiment(experiment_id, experiment)


async def delete_experiment(experiment_id: str, db: Optional[AsyncSession] = Depends(get_db)):
    service = build_experiment_service(main_module=main, db=db)
    return await service.delete_experiment(experiment_id)


router.add_api_route("/api/experiments", create_experiment, methods=["POST"], response_model=main.Experiment)
router.add_api_route("/api/experiments", list_experiments, methods=["GET"], response_model=list[main.Experiment])
router.add_api_route("/api/experiments/{experiment_id}", get_experiment, methods=["GET"], response_model=main.Experiment)
router.add_api_route("/api/experiments/{experiment_id}", update_experiment, methods=["PUT"], response_model=main.Experiment)
router.add_api_route("/api/experiments/{experiment_id}", delete_experiment, methods=["DELETE"])
