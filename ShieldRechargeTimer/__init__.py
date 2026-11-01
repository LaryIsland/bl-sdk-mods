assert __import__("mods_base").__version_info__ >= (1, 12), "Please update the SDK"
assert __import__("unrealsdk").__version_info__ >= (3, 2, 0), "Please update the SDK"

from typing import Any

import unrealsdk
from unrealsdk.unreal import BoundFunction, UObject, WrappedStruct

from mods_base import (BoolOption, CoopSupport, EInputEvent, NestedOption, SliderOption, SpinnerOption, build_mod,
                       get_pc, hook)

RedSlider = SliderOption(
    identifier="Red",
    description="Red value for the text colour.",
    value=0,
    min_value=0,
    max_value=255,
    step=1
)
GreenSlider = SliderOption(
    identifier="Green",
    description="Green value for the text colour.",
    value=160,
    min_value=0,
    max_value=255,
    step=1
)
BlueSlider = SliderOption(
    identifier="Blue",
    description="Blue value for the text colour.",
    value=255,
    min_value=0,
    max_value=255,
    step=1
)
AlphaSlider = SliderOption(
    identifier="Alpha",
    description="Alpha value for the text colour.",
    value=255,
    min_value=0,
    max_value=255,
    step=1
)
TextColour = NestedOption(
    identifier="Text Colour",
    description="Text colour for the recharge timer.",
    children=[RedSlider, GreenSlider, BlueSlider, AlphaSlider]
)
SizeSlider = SliderOption(
    identifier="Timer Size",
    description="Timer scaling as a percentage.",
    value=120,
    min_value=50,
    max_value=500,
    step=1
)
xPosSlider = SliderOption(
    identifier="X Position",
    description="X position for the timer as a percentage of the total screen.",
    value=112,
    min_value=0,
    max_value=1000,
    step=1
)
yPosSlider = SliderOption(
    identifier="Y Position",
    description="Y position for the timer as a percentage of the total screen.",
    value=860,
    min_value=0,
    max_value=1000,
    step=1
)
TimerPos = NestedOption(
    identifier="Timer Position",
    description="Text position for the recharge timer.",
    children=[xPosSlider, yPosSlider]
)
FontChoice = SpinnerOption(
    identifier="Font",
    description="Use this to pick your font.",
    value="WillowBody",
    choices=["WillowBody", "WillowHead", "HUD", "Engine 1", "Engine 2"]
)
ShowInMenu = BoolOption(
    identifier="Show in Pause Menu",
    description="When enabled, the timer will still show in the pause menu.",
    value=False
)
EnableMovement = BoolOption(
    identifier="Enable Movement Keys",
    description="When enabled, the arrow keys will move the timer and the scrollwheel will change its size.",
    value=False
)
OnlyWhenDepleted = BoolOption(
    identifier="Only when Depleted",
    description="When enabled, the timer will only show when the shield is fully depleted.",
    value=False
)
OnlyWithRoidShield = BoolOption(
    identifier="Only with Roid Shield",
    description="When enabled, the timer will only show when you have a roid shield equipped.",
    value=False
)

Fonts: list[str] = [
    "UI_Fonts.Font_Willowbody_18pt",
    "UI_Fonts.Font_Willowhead_8pt",
    "UI_Fonts.Font_Hud_Medium",
    "EngineFonts.SmallFont",
    "EngineFonts.TinyFont"
]

# The shield attributes are looked up when they're used rather than on enable
SHIELD_REGEN_DELAY: str = "D_Attributes.ShieldResourcePool.ShieldOnIdleRegenerationDelay"
SHIELD_CUR_VALUE: str = "D_Attributes.ShieldResourcePool.ShieldCurrentValue"
SHIELD_ROID_VALUE: str = "D_Attributes.Shield.RoidMeleeDamage"

TimeRemaining: float = 0.
LastDamageTakenTime: float = 0.


# Used for moving the timer while the hud is up
@hook("WillowGame.WillowUIInteraction:InputKey")
def RechargeTimerMoveKeys(
    obj: UObject,
    args: WrappedStruct,
    ret: Any,
    func: BoundFunction,
) -> None:
    if EnableMovement.value and args.Event == EInputEvent.IE_Pressed:
        if args.Key == "Up":
            yPosSlider.value -= 1
        elif args.Key == "Down":
            yPosSlider.value += 1
        elif args.Key == "Left":
            xPosSlider.value -= 1
        elif args.Key == "Right":
            xPosSlider.value += 1
        elif args.Key == "MouseScrollUp":
            SizeSlider.value += 1
        elif args.Key == "MouseScrollDown":
            SizeSlider.value -= 1
        else:
            return
        mod.save_settings()


@hook("WillowGame.WillowPlayerController:AddHUDDamageIndicator")
def RechargeTimerPlayerDamaged(
    obj: UObject,
    args: WrappedStruct,
    ret: Any,
    func: BoundFunction,
) -> None:
    global TimeRemaining, LastDamageTakenTime
    if OnlyWithRoidShield.value:
        if unrealsdk.find_object("AttributeDefinition", SHIELD_ROID_VALUE).GetValue(obj)[0] == 0.:
            return

    LastDamageTakenTime = obj.WorldInfo.TimeSeconds
    shieldCurValue = unrealsdk.find_object("ResourcePoolAttributeDefinition", SHIELD_CUR_VALUE)
    shieldDepleted = not args.bShieldOnlyDamage or shieldCurValue.GetValue(obj.Pawn)[0] <= 0
    if (not OnlyWhenDepleted.value) or shieldDepleted and (TimeRemaining <= 0):
        TimeRemaining = 1
        onPostRenderRechargeTimer.enable()
        RechargeTimerPlayerTicks.enable()


def GetTimeUntilShieldRecharge(PC: UObject) -> float:
    if PC.MyWillowPawn is None:
        return 0.

    elapsedTime = PC.MyWillowPawn.WorldInfo.TimeSeconds - LastDamageTakenTime
    if elapsedTime < 0:
        return 0.

    shieldRegenDelay = unrealsdk.find_object("ResourcePoolAttributeDefinition", SHIELD_REGEN_DELAY)
    return round(shieldRegenDelay.GetValue(PC)[0] - elapsedTime, 1)


@hook("WillowGame.WillowPlayerController:PlayerTick")
def RechargeTimerPlayerTicks(
    obj: UObject,
    args: WrappedStruct,
    ret: Any,
    func: BoundFunction,
) -> None:
    global TimeRemaining
    rechargeTime = GetTimeUntilShieldRecharge(obj)
    TimeRemaining = rechargeTime
    if rechargeTime <= 0:
        RechargeTimerPlayerTicks.disable()
        onPostRenderRechargeTimer.disable()


@hook("WillowGame.WillowGameViewportClient:PostRender")
def onPostRenderRechargeTimer(
    obj: UObject,
    args: WrappedStruct,
    ret: Any,
    func: BoundFunction,
) -> None:
    displayFeedback(args)


def DisplayText(canvas: UObject, text: float, x: float, y: float, color: tuple[float, float, float, float],
                scalex: float, scaley: float) -> None:
    fontindex = FontChoice.choices.index(FontChoice.value)
    canvas.Font = unrealsdk.find_object("Font", Fonts[fontindex])

    trueX = canvas.SizeX * x
    trueY = canvas.SizeY * y

    canvas.SetPos(trueX, trueY, 0)
    canvas.SetDrawColorStruct(unrealsdk.make_struct("Color", B=color[0], G=color[1], R=color[2], A=color[3]))
    canvas.DrawText(str(text), True, scalex, scaley)


def displayFeedback(params: WrappedStruct) -> None:
    PC = get_pc()
    if not params.Canvas:
        return

    if PC.GetHUDMovie() is None or PC.bViewingThirdPersonMenu:
        if not PC.GFxUIManager.IsMoviePlaying(PC.PauseMenuDefinition) or not ShowInMenu.value:
            return

    if PC.MyWillowPawn is None or PC.MyWillowPawn.IsInjured() or PC.MyWillowPawn.DrivenVehicle is not None:
        return

    canvas = params.Canvas
    DisplayText(
        canvas,
        TimeRemaining,
        xPosSlider.value / 1000,
        yPosSlider.value / 1000,
        (
            BlueSlider.value,
            GreenSlider.value,
            RedSlider.value,
            AlphaSlider.value
        ),
        SizeSlider.value / 100,
        SizeSlider.value / 100
    )


def onDisable() -> None:
    global TimeRemaining
    onPostRenderRechargeTimer.disable()
    RechargeTimerPlayerTicks.disable()
    # Otherwise a timer stopped part way would stop "Only when Depleted" from ever starting the next one
    TimeRemaining = 0.


mod = build_mod(
    coop_support=CoopSupport.ClientSide,
    options=[TextColour, TimerPos, SizeSlider, FontChoice, EnableMovement, ShowInMenu, OnlyWhenDepleted,
             OnlyWithRoidShield],
    hooks=[RechargeTimerPlayerDamaged, RechargeTimerMoveKeys],
    on_disable=onDisable
)
mod.description = "<font size='26' color='#de5b00'>     Shield Recharge Timer</font>\n\n" + mod.description
