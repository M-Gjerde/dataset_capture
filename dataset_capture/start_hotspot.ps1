# Windows PowerShell 5.1 / Windows 10 or 11. Invoked only with --hotspot.
$ErrorActionPreference = 'Stop'
try {
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    $null = [Windows.Networking.Connectivity.NetworkInformation, Windows.Networking.Connectivity, ContentType=WindowsRuntime]
    $null = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager, Windows.Networking.NetworkOperators, ContentType=WindowsRuntime]
    $null = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult, Windows.Networking.NetworkOperators, ContentType=WindowsRuntime]

    function Wait-Action($Action) {
        $method = [System.WindowsRuntimeSystemExtensions].GetMethods() |
            Where-Object {
                $_.Name -eq 'AsTask' -and -not $_.IsGenericMethod -and
                $_.GetParameters().Count -eq 1 -and
                $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncAction'
            } | Select-Object -First 1
        $task = $method.Invoke($null, @($Action))
        if (-not $task.Wait(30000)) { throw 'Hotspot configuration timed out.' }
        $task.GetAwaiter().GetResult()
    }

    function Wait-Operation($Operation) {
        $method = [System.WindowsRuntimeSystemExtensions].GetMethods() |
            Where-Object {
                $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and
                $_.GetGenericArguments().Count -eq 1 -and
                $_.GetParameters().Count -eq 1 -and
                $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
            } | Select-Object -First 1
        $method = $method.MakeGenericMethod([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])
        $task = $method.Invoke($null, @($Operation))
        if (-not $task.Wait(30000)) { throw 'Starting Mobile hotspot timed out.' }
        return $task.GetAwaiter().GetResult()
    }

    $profile = [Windows.Networking.Connectivity.NetworkInformation]::GetInternetConnectionProfile()
    if ($null -eq $profile) { throw 'Connect this PC to an upstream network first (Ethernet is preferred).' }
    $manager = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($profile)
    $config = $manager.GetCurrentAccessPointConfiguration()
    if ($manager.TetheringOperationalState.ToString() -eq 'On') {
        if ($config.Ssid -eq 'DatasetCapture' -and $config.Passphrase -eq 'datasetcapture') {
            if ($null -ne $config.PSObject.Properties['Band'] -and $config.Band.ToString() -ne 'TwoPointFourGigahertz') {
                throw 'DatasetCapture is active on another band. Turn it off before using --hotspot.'
            }
            if ($null -ne $config.PSObject.Properties['AuthenticationKind'] -and $config.AuthenticationKind.ToString() -ne 'Wpa2') {
                throw 'DatasetCapture is active with another security mode. Turn it off before using --hotspot.'
            }
            Write-Output 'DatasetCapture is already enabled.'
            exit 0
        }
        throw 'Another hotspot is active. Turn it off in Windows Settings before using --hotspot.'
    }
    $config.Ssid = 'DatasetCapture'
    $config.Passphrase = 'datasetcapture'
    if ($null -ne $config.PSObject.Properties['Band']) {
        $band = [Windows.Networking.NetworkOperators.TetheringWiFiBand, Windows.Networking.NetworkOperators, ContentType=WindowsRuntime]::TwoPointFourGigahertz
        if (-not $config.IsBandSupported($band)) { throw 'This adapter cannot host a 2.4 GHz hotspot.' }
        $config.Band = $band
    }
    # AuthenticationKind exists on newer Windows releases; older releases use WPA2.
    if ($null -ne $config.PSObject.Properties['AuthenticationKind']) {
        $auth = [Windows.Networking.NetworkOperators.TetheringWiFiAuthenticationKind, Windows.Networking.NetworkOperators, ContentType=WindowsRuntime]::Wpa2
        if (-not $config.IsAuthenticationKindSupported($auth)) { throw 'This adapter cannot host a WPA2 hotspot.' }
        $config.AuthenticationKind = $auth
    }
    Wait-Action ($manager.ConfigureAccessPointAsync($config))
    $result = Wait-Operation ($manager.StartTetheringAsync())
    if ($result.Status.ToString() -ne 'Success') {
        throw ("Mobile hotspot failed: {0}. {1}" -f $result.Status, $result.AdditionalErrorMessage)
    }
    if ($manager.TetheringOperationalState.ToString() -ne 'On') { throw 'Windows did not enable Mobile hotspot.' }
    Write-Output 'DatasetCapture started (password: datasetcapture).'
} catch {
    [Console]::Error.WriteLine("Windows hotspot: " + $_.Exception.Message + " Check Settings > Network & internet > Mobile hotspot and adapter/policy support.")
    exit 1
}
