from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Plant, utcnow
from ..schemas import PlantCreate, PlantUpdate, PlantResponse

router = APIRouter(prefix="/api/plants", tags=["Plant Management"])


@router.get("", response_model=List[PlantResponse])
def get_plants(db: Session = Depends(get_db)):
    """List all registered plants in the garden collection."""
    return db.query(Plant).order_by(Plant.created_at.desc()).all()


@router.post("", response_model=PlantResponse, status_code=201)
def create_plant(plant_in: PlantCreate, db: Session = Depends(get_db)):
    """Register a new plant with its preferred moisture ranges and threshold."""
    plant = Plant(
        name=plant_in.name,
        plant_type=plant_in.plant_type,
        location=plant_in.location,
        preferred_moisture_min=plant_in.preferred_moisture_min,
        preferred_moisture_max=plant_in.preferred_moisture_max,
        irrigation_threshold=plant_in.irrigation_threshold,
        notes=plant_in.notes or "",
        created_at=utcnow(),
    )
    db.add(plant)
    db.commit()
    db.refresh(plant)
    return plant


@router.put("/{plant_id}", response_model=PlantResponse)
def update_plant(plant_id: int, plant_in: PlantUpdate, db: Session = Depends(get_db)):
    """Update profile and watering requirements for an existing plant."""
    plant = db.query(Plant).filter(Plant.id == plant_id).first()
    if not plant:
        raise HTTPException(status_code=404, detail="Plant not found")

    if plant_in.name is not None:
        plant.name = plant_in.name
    if plant_in.plant_type is not None:
        plant.plant_type = plant_in.plant_type
    if plant_in.location is not None:
        plant.location = plant_in.location
    if plant_in.preferred_moisture_min is not None:
        plant.preferred_moisture_min = plant_in.preferred_moisture_min
    if plant_in.preferred_moisture_max is not None:
        plant.preferred_moisture_max = plant_in.preferred_moisture_max
    if plant_in.irrigation_threshold is not None:
        plant.irrigation_threshold = plant_in.irrigation_threshold
    if plant_in.notes is not None:
        plant.notes = plant_in.notes

    db.commit()
    db.refresh(plant)
    return plant


@router.delete("/{plant_id}")
def delete_plant(plant_id: int, db: Session = Depends(get_db)):
    """Remove a plant record from the database."""
    plant = db.query(Plant).filter(Plant.id == plant_id).first()
    if not plant:
        raise HTTPException(status_code=404, detail="Plant not found")

    db.delete(plant)
    db.commit()
    return {"status": "deleted", "plant_id": plant_id}
