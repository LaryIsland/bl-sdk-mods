import webbrowser

from unrealsdk import (FindObject, FStruct, GetEngine, Log,  # type: ignore
                       RemoveHook, RunHook, UFunction, UObject)

from ..ModMenu import (EnabledSaveType, Game, Mods, ModTypes, Options,
                       RegisterMod, SDKMod)


# used for moving the timer while the hud is up
def RechargeTimerMoveKeys(caller: UObject, function: UFunction, params: FStruct):
    if instance.EnableMovement.CurrentValue and params.Event == 0:
        if params.Key == "Up":
            instance.yPosSlider.CurrentValue -= 1
        if params.Key == "Down":
            instance.yPosSlider.CurrentValue += 1
        if params.Key == "Left":
            instance.xPosSlider.CurrentValue -= 1
        if params.Key == "Right":
            instance.xPosSlider.CurrentValue += 1
        if params.Key == "MouseScrollUp":
            instance.SizeSlider.CurrentValue += 1
        if params.Key == "MouseScrollDown":
            instance.SizeSlider.CurrentValue -= 1
    return True


def RechargeTimerPlayerDamaged(caller: UObject, function: UFunction, params: FStruct) -> bool:
    if instance.OnlyWithRoidShield.CurrentValue:
        if instance.ShieldRoidValue.GetValue(caller.Controller)[0] == 0.:
            return True

    instance.LastDamageTakenTime = caller.WorldInfo.TimeSeconds
    if (not instance.OnlyWhenDepleted.CurrentValue) or (params.Damage >= instance.ShieldCurValue.GetValue(caller)[0]) \
            and (instance.TimeRemaining <= 0):
        instance.TimeRemaining = 1
        RunHook("WillowGame.WillowGameViewportClient.PostRender", "PostRenderRechargeTimer", onPostRenderRechargeTimer)
        RunHook("WillowGame.WillowPlayerController.PlayerTick", "RechargeTimerPlayerTicks", RechargeTimerPlayerTicks)
    return True


def GetTimeUntilShieldRecharge(PC) -> float:
    try:
        # resets timer if you quit whilst your shield is recharging and switch character
        elapsedTime = PC.MyWillowPawn.WorldInfo.TimeSeconds - instance.LastDamageTakenTime
        if elapsedTime < 0:
            return 0.
    except AttributeError:
        return 0.

    return round(instance.ShieldRegenDelay.GetValue(PC)[0] - elapsedTime, 1)


def RechargeTimerPlayerTicks(caller: UObject, function: UFunction, params: FStruct) -> bool:
    rechargeTime = GetTimeUntilShieldRecharge(caller)
    instance.TimeRemaining = rechargeTime
    if rechargeTime <= 0:
        RemoveHook("WillowGame.WillowPlayerController.PlayerTick", "RechargeTimerPlayerTicks")
        RemoveHook("WillowGame.WillowGameViewportClient.PostRender", "PostRenderRechargeTimer")
    return True


def onPostRenderRechargeTimer(caller: UObject, function: UFunction, params: FStruct) -> bool:
    instance.displayFeedback(params)
    return True


class ShieldRechargeTimer(SDKMod):
    Name: str = "Shield Recharge Timer"
    Author: str = "LaryIsland"
    Description: str = (
        "<font size='26' color='#de5b00'>     Shield Recharge Timer</font>\n\n"
        "Displays a configurable timer on your HUD that counts the seconds before your shield starts to recharge.\n\n"
    )
    Version: str = "1.0"

    SupportedGames: Game = Game.BL2 | Game.TPS
    Types: ModTypes = ModTypes.Utility
    SaveEnabledState: EnabledSaveType = EnabledSaveType.LoadOnMainMenu

    SettingsInputs = SDKMod.SettingsInputs.copy()
    SettingsInputs["G"] = "GitHub"

    def SettingsInputPressed(self, action: str) -> None:
        if action == "GitHub":
            webbrowser.open("https://github.com/LaryIsland/bl-sdk-mods/tree/main/ShieldRechargeTimer")
        else:
            super().SettingsInputPressed(action)

    TimeRemaining: float = 0.
    LastDamageTakenTime: float = 0.

    def __init__(self) -> None:
        self.Options = []
        self.RedSlider = Options.Slider(
            Caption="Red",
            Description="Red value for the text colour.",
            StartingValue=0,
            MinValue=0,
            MaxValue=255,
            Increment=1,
            IsHidden=False
        )
        self.GreenSlider = Options.Slider(
            Caption="Green",
            Description="Green value for the text colour.",
            StartingValue=160,
            MinValue=0,
            MaxValue=255,
            Increment=1,
            IsHidden=False
        )
        self.BlueSlider = Options.Slider(
            Caption="Blue",
            Description="Blue value for the text colour.",
            StartingValue=255,
            MinValue=0,
            MaxValue=255,
            Increment=1,
            IsHidden=False
        )
        self.AlphaSlider = Options.Slider(
            Caption="Alpha",
            Description="Alpha value for the text colour.",
            StartingValue=255,
            MinValue=0,
            MaxValue=255,
            Increment=1,
            IsHidden=False
        )
        self.TextColour = Options.Nested(
            Caption="Text Colour",
            Description="Text colour for the recharge timer.",
            Children=[self.RedSlider, self.GreenSlider, self.BlueSlider, self.AlphaSlider],
            IsHidden=False
        )
        self.SizeSlider = Options.Slider(
            Caption="Timer Size",
            Description="Timer scaling as a percentage.",
            StartingValue=120,
            MinValue=50,
            MaxValue=500,
            Increment=1,
            IsHidden=False
        )
        self.xPosSlider = Options.Slider(
            Caption="X Position",
            Description="X position for the timer as a percentage of the total screen.",
            StartingValue=112,
            MinValue=0,
            MaxValue=1000,
            Increment=1,
            IsHidden=False
        )
        self.yPosSlider = Options.Slider(
            Caption="Y Position",
            Description="Y position for the timer as a percentage of the total screen.",
            StartingValue=484,
            MinValue=0,
            MaxValue=1000,
            Increment=1,
            IsHidden=False
        )
        self.TimerPos = Options.Nested(
            Caption="Timer Position",
            Description="Text position for the recharge timer.",
            Children=[self.xPosSlider, self.yPosSlider],
            IsHidden=False
        )
        self.FontChoice = Options.Spinner(
            Caption="Font",
            Description="Use this to pick your font.",
            StartingValue="WillowBody",
            Choices=["WillowBody",
                     "WillowHead",
                     "HUD",
                     "Engine 1",
                     "Engine 2"]
        )
        self.ShowInMenu = Options.Boolean(
            Caption="Show in Pause Menu",
            Description="When enabled, the timer will still show in the pause menu.",
            StartingValue=False,
        )
        self.EnableMovement = Options.Boolean(
            Caption="Enable Movement Keys",
            Description="When enabled, the arrow keys will move the timer and the scrollwheel will change its size.",
            StartingValue=False,
        )
        self.OnlyWhenDepleted = Options.Boolean(
            Caption="Only when Depleted",
            Description="When enabled, the timer will only show when the shield is fully depleted.",
            StartingValue=False,
        )
        self.OnlyWithRoidShield = Options.Boolean(
            Caption="Only with Roid Shield",
            Description="When enabled, the timer will only show when you have a roid shield equipped.",
            StartingValue=False,
        )
        self.Options = [
            self.TextColour,
            self.TimerPos,
            self.SizeSlider,
            self.FontChoice,
            self.EnableMovement,
            self.ShowInMenu,
            self.OnlyWhenDepleted,
            self.OnlyWithRoidShield
        ]

    def DisplayText(self, canvas, text, x, y, color, scalex, scaley) -> None:
        fontindex = self.FontChoice.Choices.index(self.FontChoice.CurrentValue)
        canvas.Font = FindObject("Font", self.Fonts[fontindex])

        trueX = canvas.SizeX * x
        trueY = canvas.SizeX * y

        canvas.SetPos(trueX, trueY, 0)

        try:
            canvas.SetDrawColorStruct(color)
        except Exception:
            pass

        canvas.DrawText(str(text), True, scalex, scaley)

    def displayFeedback(self, params):
        PC = GetEngine().GamePlayers[0].Actor
        if not params.Canvas:
            return True

        if PC.GetHUDMovie() is None or PC.bViewingThirdPersonMenu:
            if not PC.GFxUIManager.IsMoviePlaying(PC.PauseMenuDefinition) or not self.ShowInMenu.CurrentValue:
                return True

        if PC.MyWillowPawn.IsInjured() or PC.MyWillowPawn.DrivenVehicle is not None:
            return True

        canvas = params.Canvas
        self.DisplayText(
            canvas,
            self.TimeRemaining,
            self.xPosSlider.CurrentValue / 1000,
            self.yPosSlider.CurrentValue / 1000,
            (
                self.BlueSlider.CurrentValue,
                self.GreenSlider.CurrentValue,
                self.RedSlider.CurrentValue,
                self.AlphaSlider.CurrentValue
            ),
            self.SizeSlider.CurrentValue / 100,
            self.SizeSlider.CurrentValue / 100
        )
        return True

    def Enable(self):
        RunHook("WillowGame.WillowPlayerPawn.TakeDamage", "RechargeTimerPlayerDamaged", RechargeTimerPlayerDamaged)
        RunHook("WillowGame.WillowUIInteraction.InputKey", "RechargeTimerMoveKeys", RechargeTimerMoveKeys)
        self.ShieldRegenDelay = FindObject(
            "ResourcePoolAttributeDefinition",
            "D_Attributes.ShieldResourcePool.ShieldOnIdleRegenerationDelay"
        )
        self.ShieldCurValue = FindObject(
            "ResourcePoolAttributeDefinition",
            "D_Attributes.ShieldResourcePool.ShieldCurrentValue"
        )
        self.ShieldRoidValue = FindObject(
            "AttributeDefinition",
            "D_Attributes.Shield.RoidMeleeDamage"
        )
        self.Fonts = [
            "UI_Fonts.Font_Willowbody_18pt",
            "UI_Fonts.Font_Willowhead_8pt",
            "UI_Fonts.Font_Hud_Medium",
            "EngineFonts.SmallFont",
            "EngineFonts.TinyFont"
        ]

    def Disable(self):
        RemoveHook("WillowGame.WillowGameViewportClient.PostRender", "PostRenderRechargeTimer")
        RemoveHook("WillowGame.WillowPlayerPawn.TakeDamage", "RechargeTimerPlayerDamaged")


instance = ShieldRechargeTimer()

if __name__ == "__main__":
    Log(f"[{instance.Name}] Manually loaded")
    for mod in Mods:
        if mod.Name == instance.Name:
            if mod.IsEnabled:
                mod.Disable()
            Mods.remove(mod)
            Log(f"[{instance.Name}] Removed last instance")

            # Fixes inspect.getfile()
            instance.__class__.__module__ = mod.__class__.__module__
            break

RegisterMod(instance)
