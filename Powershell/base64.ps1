
Function Base64(){
Param(
    [Parameter(ValueFromPipeline=$true)]
    $Decode,
    [Parameter(ValueFromPipeline=$true)]
    $Encode
)

    if(($Decode -ne $null -or $Decode -ne "") -and ($Encode -eq $null -or $Encode -eq "")){
        try{
            $result = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($Decode))
        }catch{
            
        }
    }elseif(($Decode -eq $null -or $Decode -eq "") -and ($Encode -ne $null -or $Encode -ne "")){
            try{
                $result = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Encode))
            }catch{

            }
    }

    return $result

}