pipeline {
  agent any

  // No TEST_TARGET param on purpose
  parameters {
    string(name: 'DEVICES',    defaultValue: '', description: 'Serial(s)/IP(s); space or comma separated')
    text  (name: 'AUTH_TXT',   defaultValue: '',             description: 'Auth header text')
    text  (name: 'COOKIE_TXT', defaultValue: '',             description: 'Cookie header text')
    booleanParam(name: 'ARCHIVE_ZIPS', defaultValue: true, description: 'Archive any *.zip downloads')
  }

  environment {
    SEVEN_ZIP            = "C:\\Program Files\\7-Zip\\7z.exe"
    DEFAULT_TEST_TARGET  = "tests_device_mode"   // CI-safe default if TEST_TARGET is empty
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
        bat 'if not exist downloaded_bugreports mkdir downloaded_bugreports'
        script {
          writeFile file: 'config/auth.txt',    text: params.AUTH_TXT   ?: ''
          writeFile file: 'config/cookie.txt',  text: params.COOKIE_TXT ?: ''
          writeFile file: 'config/devices.txt', text: params.DEVICES    ?: ''
        }
      }
    }

    stage('Run tests (one suite, one time)') {
      steps {
        bat """
          setlocal enabledelayedexpansion

          rem ---- pass other params ----
          set DEVICES=%DEVICES%
          set SEVEN_ZIP=%SEVEN_ZIP%

          rem ---- IMPORTANT: You removed the TEST_TARGET param.
          rem If TEST_TARGET is empty, Jenkins machines have no "focused app",
          rem and your tests_run.py 'auto' path can trigger extra polling.
          rem To keep ONE suite/ONE run in CI, force a safe default ONLY on Jenkins.
          if "%TEST_TARGET%"=="" (
            if not "%JENKINS_URL%"=="" (
              set TEST_TARGET=%DEFAULT_TEST_TARGET%
            )
          )

          echo DEVICES=%DEVICES%
          echo TEST_TARGET=%TEST_TARGET%   (empty means tests_run will decide)

          .venv\\Scripts\\python.exe tests_run.py
        """
      }
    }
  }

  post {
    always {
      junit allowEmptyResults: true, testResults: 'reports/**/*.xml'
      archiveArtifacts artifacts: 'reports/*.html, downloaded_bugreports/**/*.zip, **/debugarchive_*.zip',
                        fingerprint: true, onlyIfSuccessful: false

      publishHTML(target: [
        reportDir: 'reports',
        reportFiles: 'report_*.html',
        reportName: "Crash Analytics – HTML Reports",
        keepAll: true,
        allowMissing: true,
        alwaysLinkToLastBuild: true
      ])
    }
  }
}
