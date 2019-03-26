function updatePlatform(platform) {
    $.ajax({
        url: "/update/" + platform,
        cache: false,
        timeout: 25000
    })
        .done(function( data ) {
            if( Object.keys(data).length == 0 ) return;
            for (var task_id in data) {
                row = $("tr[data-id='" + task_id + "']")
                row_data = data[task_id]
                // Status
                status = row_data['status'];
                $("td[data-col='status']", row).html(status).removeClass('updating').addClass(status);
                // Epoch
                $("td[data-col='epoch']", row).html((row_data['epoch'] + 1) + ' / ' + row_data['total_epochs']).removeClass('updating');
                // Iteration
                $("td[data-col='iteration']", row).html((row_data['iter'] + 1) + ' / ' + row_data['iter_per_epoch']).removeClass('updating');
            }
        })
        .fail(function( jqXHR, textStatus ) {
            console.log('Update request has failed: ' + textStatus);
            console.log(jqXHR);
        });
}

$( document ).ready(function() {
    $('table').tablesort()
    $('thead th.number').data(
        'sortBy',
        function(th, td, tablesort) {
            return parseFloat(td.text());
        }
    );
    $('#checkall').click(function(event) {
        $('.toggle-job').prop('checked', $(this).prop('checked'));
        event.stopPropagation();
    });
    $('tr').click(function() {
        checkbox = $('.toggle-job', this);
        checkbox.prop('checked', !checkbox.prop('checked'));
    });
    $('.toggle-job').click(function(event) {
        event.stopPropagation();
    });
    $('.button').click(function(event) {
        $(this).addClass('loading');
        event.stopPropagation();
    });
    $('td.updating').append('<div class="ui active tiny inline loader"></div>');

    // Update table
    $.ajax({
        url: "/enum",
        cache: false
    })
        .done(function( platform_names ) {
            platform_names.forEach(function(p){
                updatePlatform(p);
            });
        });
});