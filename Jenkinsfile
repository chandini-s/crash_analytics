pipeline {
  agent any
  options { timestamps(); ansiColor('xterm') }

  // Parameters (pre-filled every time; you can just press Build)
  parameters {
    string(name: 'DEVICES',    defaultValue: '', description: 'Serial(s)/IP(s); space or comma separated')
    text  (name: 'AUTH_TXT',   defaultValue: '',             description: 'Auth header text')
    text  (name: 'COOKIE_TXT', defaultValue: '',             description: 'Cookie header text')
    choice(name: 'TEST_SUITE', choices: ['tests_mtr','tests_zoom','tests_oobe'], description: 'Single suite to run')
    booleanParam(name: 'ARCHIVE_ZIPS', defaultValue: true, description: 'Archive any *.zip downloads')
  }

  environment {
    SEVEN_ZIP = "C:\\Program Files\\7-Zip\\7z.exe"
  }

  stages {
    stage('Checkout') { steps { checkout scm } }

    stage('Python venv & deps (Windows)') {
      steps {
        bat '''
          if not exist .venv\\Scripts\\python.exe (
            py -3 -m venv .venv
          )
          .venv\\Scripts\\python.exe -m pip install --upgrade pip
          if exist requirements.txt (
            .venv\\Scripts\\pip.exe install -r requirements.txt
          ) else (
            .venv\\Scripts\\pip.exe install pytest pytest-html requests
          )
        '''
      }
    }

    stage('Prepare config & folders') {
      steps {
        bat 'if not exist config mkdir config'
        bat 'if not exist reports mkdir reports'
        bat 'if not exist downloads mkdir downloads'
        // Use Jenkins writeFile so special characters in headers are safe on Windows
        script {
          writeFile file: 'config/auth.txt',   text: params.AUTH_TXT ?: ''
          writeFile file: 'config/cookie.txt', text: params.COOKIE_TXT ?: ''
          writeFile file: 'config/devices.txt', text: params.DEVICES ?: ''
        }
      }
    }

    stage('Run tests (one suite, one time)') {
      steps {
        bat """
          setlocal enabledelayedexpansion
          set DEVICES=%DEVICES%
          set TEST_TARGET=%TEST_SUITE%
          set SEVEN_ZIP=%SEVEN_ZIP%

          echo === Running %TEST_TARGET% ===
          .venv\\Scripts\\python.exe tests_run.py

          rem If your suite already created an HTML in reports\\report_*.html this is a no-op.
          rem Fallback: generate a minimal pytest HTML so publishHTML always has something.
          dir /b reports\\report_%TEST_TARGET%_*.html >nul 2>&1
          if errorlevel 1 (
            echo No suite HTML found, creating one via pytest...
            .venv\\Scripts\\pytest.exe %TEST_TARGET% -q --maxfail=1 --html "reports\\report_%TEST_TARGET%_%BUILD_NUMBER%.html" --self-contained-html
          )
        """
      }
    }
  }

  post {
    always {
      junit allowEmptyResults: true, testResults: 'reports/**/*.xml'
      archiveArtifacts artifacts: 'reports/*.html, downloads/**/*.zip, **/debugarchive_*.zip', fingerprint: true, onlyIfSuccessful: false
      publishHTML(target: [
        reportDir: 'reports',
        reportFiles: 'report_*.html',
        reportName: "Crash Analytics – ${params.TEST_SUITE}",
        keepAll: true,
        allowMissing: true,
        alwaysLinkToLastBuild: true
      ])
    }
  }
}
