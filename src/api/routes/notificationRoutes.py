from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.dependencies.auth import getCurrentUser
from api.dependencies.database import getDbWithRLS
from schemas.notificationSchemas import NotificationResponse
from domain.services.notificationService import NotificationService
from exceptions.baseExceptions import NoHarmException
from security.limiter import limiter


router = APIRouter(prefix="/notifications", tags=["Notifications"])


class DeviceBody(BaseModel):
    deviceFCM: str = Field(..., description="FCM device token")


class UpdateDeviceBody(BaseModel):
    newFCM: str = Field(..., description="New FCM device token")


@router.post(
    "",
    response_model=NotificationResponse,
    status_code=201,
    summary="Register device for notifications",
    description="Register an FCM device token to receive push notifications."
)
@limiter.limit("10/minute")
def addDevice(
    request: Request,
    body: DeviceBody,
    db=Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = NotificationService(db)
        notification = service.addDevice(currentUserId, body.deviceFCM)
        return NotificationResponse.model_validate(notification)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.put(
    "/{oldFCM}",
    response_model=NotificationResponse,
    summary="Update device token",
    description="Replace an existing FCM token with a new one."
)
@limiter.limit("10/minute")
def updateDevice(
    request: Request,
    oldFCM: str,
    body: UpdateDeviceBody,
    db=Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = NotificationService(db)
        notification = service.updateDevice(currentUserId, oldFCM, body.newFCM)
        return NotificationResponse.model_validate(notification)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.delete(
    "/{fcmToken}",
    status_code=204,
    summary="Unregister device",
    description="Remove an FCM device token from the notification registry."
)
@limiter.limit("10/minute")
def deleteDevice(
    request: Request,
    fcmToken: str,
    db=Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = NotificationService(db)
        service.deleteDevice(currentUserId, fcmToken)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
