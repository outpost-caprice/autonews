function postToWordpress() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var rows = sheet.getDataRange().getValues();
  var headers = rows.shift(); // 最初の行はヘッダーとして扱う

  rows.forEach(function(row, index) {
    var postData = {};
    headers.forEach(function(header, i) {
      postData[header] = row[i];
    });

    // WordPressのAPIエンドポイント
    var endpoint = 'https://yourwordpresssite.com/wp-json/wp/v2/posts';
    var options = {
      method: 'post',
      contentType: 'application/json',
      headers: {
        'Authorization': 'Bearer YOUR_ACCESS_TOKEN' // トークンをセット
      },
      payload: JSON.stringify({
        title: postData['Title'],
        content: postData['Content'],
        status: 'publish'
      })
    };

    // 新しい行の場合は投稿を作成
    if (!postData['ID']) {
      var response = UrlFetchApp.fetch(endpoint, options);
      var responseData = JSON.parse(response.getContentText());
      // スプレッドシートにWordPressの投稿IDを保存
      sheet.getRange(index + 2, headers.indexOf('ID') + 1).setValue(responseData.id);
    } else {
      // 既存の行の場合は投稿を更新
      UrlFetchApp.fetch(endpoint + '/' + postData['ID'], options);
    }
  });
}

function deleteOldRows() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var rows = sheet.getDataRange().getValues();
  var today = new Date();
  var sevenDaysAgo = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 7);

  rows.forEach(function(row, index) {
    var date = new Date(row[0]); // 日付は最初の列にあると仮定
    if (date < sevenDaysAgo) {
      sheet.deleteRow(index + 1); // 行は1から始まるので+1
    }
  });
}

function setupTriggers() {
  // トリガーを設定して、postToWordpress関数を定期的に実行
  ScriptApp.newTrigger('postToWordpress')
    .timeBased()
    .everyHours(1) // 1時間ごとに実行、必要に応じて変更
    .create();

  // トリガーを設定して、deleteOldRows関数を毎日実行
  ScriptApp.newTrigger('deleteOldRows')
    .timeBased()
    .atHour(1) // 毎日1時に実行、必要に応じて変更
    .everyDays(1)
    .create();
}
