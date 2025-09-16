pipeline {
  agent { label 'window' }
  options {
  buildDiscarder(logRotator(numToKeepStr: '50'))
  wrap([$class: 'AnsiColorBuildWrapper', colorMapName: 'xterm'])
}



  parameters {
    string(name: 'DEVICES',
           defaultValue: '10.91.231.25, 10.91.231.82',
           description: 'Devices to use. Comma/space separated IPs, or a full JSON array like [{"setup":"10.0.0.1"}, ...].')

    choice(name: 'TEST_TARGET',
           choices: ['auto','tests_mtr','tests_zoom','tests_oobe','tests_device_mode'],
           description: 'auto = run tests_run.py (it decides); otherwise run a specific folder.')

    booleanParam(name: 'CLEAN_EXTRACT_DIR', defaultValue: true,
                 description: 'Delete downloaded_bugreports / extracted_bugreports before each run.')
  }

  environment {
    VENV      = '.venv'
    ADB_HOME  = 'C:\\Android\\platform-tools'
    SEVEN_ZIP = 'C:\\Program Files\\7-Zip\\7z.exe'
    PATH      = "${env.PATH};${ADB_HOME}"
  }

  stages {
    stage('Checkout') { steps { checkout(scm) } }

    stage('Python venv') {
      steps {
        bat '''
          py -3 -m venv %VENV%
          call %VENV%\\Scripts\\activate
          python -m pip install --upgrade pip
          if exist requirements.txt pip install -r requirements.txt
        '''
      }
    }

    stage('Auth/Cookie from Jenkins credentials') {
      steps {
        withCredentials([
          string(credentialsId: 'ca_auth_txt',   variable: 'AUTH_TXT'),
          string(credentialsId: 'ca_cookie_txt', variable: 'COOKIE_TXT')
        ]) {
          bat '''
            if not exist config mkdir config
            powershell -NoProfile -Command "$env:AUTH_TXT   | Out-File -FilePath 'config\\auth.txt'   -Encoding ascii"
            powershell -NoProfile -Command "$env:COOKIE_TXT | Out-File -FilePath 'config\\cookie.txt' -Encoding ascii"
          '''
        }
      }
    }

    stage('Build DEVICES_JSON (no files)') {
      steps {
        script {
          def raw = (params.DEVICES ?: '').trim()
          if (!raw) {
            error "DEVICES parameter is empty."
          }
          // If user pasted JSON, keep it; otherwise build [{"setup":"ip"}, ...]
          def json = raw.startsWith('[') ?
                     raw :
                     '[' + raw.split(/[\s,;]+/)
                              .findAll { it }
                              .collect { "{\"setup\":\"${it}\"}" }
                              .join(',') + ']'
          env.DEVICES_JSON = json
          echo "Using DEVICES_JSON: ${json}"
        }
      }
    }

    stage('Lab prep + ADB connect') {
      steps {
        bat """
          if "${params.CLEAN_EXTRACT_DIR}"=="true" (
            if exist downloaded_bugreports rmdir /S /Q downloaded_bugreports
            if exist extracted_bugreports  rmdir /S /Q extracted_bugreports
          )
          mkdir downloaded_bugreports 2>NUL
          mkdir extracted_bugreports  2>NUL
        """
        bat '''
          powershell -NoProfile -Command ^
            "$d = $env:DEVICES_JSON | ConvertFrom-Json; ^
             foreach ($x in $d) { $ip=$x.setup; if ($ip) { ^
               & adb disconnect $ip *> $null; ^
               & adb connect $ip; ^
             }}; ^
             & adb devices"
        '''
      }
    }

    stage('Run tests') {
      steps {
        script {
          def cmd = (params.TEST_TARGET == 'auto')
            ? 'pytest -q tests_run.py --junitxml=reports\\junit.xml -r fEsx'
            : "pytest -q ${params.TEST_TARGET} --junitxml=reports\\junit.xml -r fEsx"
          bat """
            call %VENV%\\Scripts\\activate
            set SEVEN_ZIP=%SEVEN_ZIP%
            set DEVICES_JSON=%DEVICES_JSON%
            ${cmd}
          """
        }
      }
      post {
        always {
          archiveArtifacts artifacts: 'reports\\**; downloaded_bugreports\\**; extracted_bugreports\\**', allowEmptyArchive: true
          junit 'reports\\junit.xml'
        }
      }
    }
  }

  post {
    always {
      bat '''
        powershell -NoProfile -Command ^
          "$d = $env:DEVICES_JSON | ConvertFrom-Json; ^
           foreach ($x in $d) { $ip=$x.setup; if ($ip) { & adb disconnect $ip *> $null }}"
      '''
    }
  }
}